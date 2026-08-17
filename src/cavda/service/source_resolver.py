from __future__ import annotations

import json
from typing import Any

from cavda.dto.errors import IntentParseError
from cavda.dto.models import Candidate, UserIntent

__all__ = ["resolve_sources"]

from cavda.util.ai_utils import build_ai_client

MODEL = "claude-sonnet-5"
MAX_TOKENS = 6000
MAX_SEARCHES = 3

SYSTEM_PROMPT = """\
Find candidate pages hosting a specific video (movie or TV episode) based on exact parameters that user provided \
using the web_search tool, restricted to an allow-listed set of domains.

<input>
You will receive a structured search intent with next fields: title, season, \
episode, quality, language. Any field except title may be null — a null field means the \
user did not specify it and must not be assumed.
</input>

<search_strategy>
- Build search queries from the intent fields that are non-null. Always \
  include the title. Include season/episode using the site-appropriate \
  format (e.g. "season 1 episode 2", "s01e02") if given.
- If language is given, search in that language and prefer results whose \
  page content is actually in that language — a page merely mentioning the \
  language does not satisfy the request. Do not use "quality" field to filter results.
- Issue multiple queries with different phrasings if the first search does \
  not clearly resolve the title (e.g. localized title, alternate spelling).
</search_strategy>

<constraints>
- Never propose a URL you did not receive from a web_search result. Do not \
create, guess, complete, shorten, extend, or "fix" a URL. Copy it exactly as \
the search result gave it to you.
- For every candidate, you must find in evidence: result page must contain requested title (and season/episode, if given).
Propose a page only if the search result gives concrete evidence it \
contains the requested title. If the evidence is about a different work, a \
trailer, a review, a listing/category page, or you simply cannot tell, leave \
it out.
- `url` must be the page's link not invented or changed one\
- `title` must be the page's own title as it appears in the search result or \
page content — never invent or reword it into something more generic.
- `description` must be a brief description (not more than 200 characters) of the content taken from the \
site itself (e.g. a synopsis shown in the search snippet or page). If the \
search result gives no such description, set it to null — do not write your \
own summary or invent one.
- If nothing meets these rules, call the tool with an empty candidates list. \
Returning nothing is a correct and expected outcome. Never pad the list.
</constraints>

<output>
When you are done searching, report your candidates by calling the \
propose_candidates tool exactly once.
</output>

<example>
Intent: {"title": "Ultimate Note", "season": 1, "episode": 1, "quality": null, "language": null}

A qualifying candidate:
{
  "url": "https://www.iq.com/play/ultimate-note-episode-1-1a0si8jnra4",
  "title": "Ultimate Note",
  "description": "Curious about his uncle’s past, Wu Xie watched a mysterious video tape only to find himself...",
}
</example>
"""

CANDIDATE_TOOL = {
    "name": "propose_candidates",
    "description": (
        "Report the candidate pages found via web_search."
        "Pass an empty list if nothing qualifies."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": (
                                "The URL exactly as it appeared in a web_search "
                                "result. Never constructed or edited."
                            ),
                        },
                        "title": {
                            "type": "string",
                            "description": (
                                "The page's own title, as shown in the search "
                                "result or page content — not a paraphrase."
                            ),
                        },
                        "description": {
                            "type": ["string", "null"],
                            "description": (
                                "Brief description (not more than 200 characters) of the video "
                                "taken from the site's own content. Null if the search result "
                                "gave no such description — never invented."
                            ),
                        },
                    },
                    "required": ["url", "title", "description"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    },
    "strict": True,
}


def resolve_sources(intent: UserIntent, allowlist: set[str]) -> list[Candidate]:
    """Ask AI for candidate pages, restricted to ``allowlist``."""
    client = build_ai_client()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(intent)}],
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "allowed_domains": sorted(allowlist),  # use sorted list to be able to cache it
                "max_uses": MAX_SEARCHES,
            },
            CANDIDATE_TOOL,
        ],
    )

    items = _get_proposed_candidates_block(response)
    return _convert_items_to_candidates(items)


def _build_user_message(intent: UserIntent) -> str:
    lines = ["Search for a video based on the parameters listed below. "
             "Use only the allowed domains and report pages that host this exact video.",
             f"Title: {intent.title}"]
    if intent.season is not None:
        lines.append(f"Season: {intent.season}")
    if intent.episode is not None:
        lines.append(f"Episode: {intent.episode}")
    if intent.language:
        lines.append(f"Preferred language: {intent.language}")
    if intent.quality:
        lines.append(f"Preferred quality: {intent.quality}")

    return "\n".join(lines)


def _convert_items_to_candidates(items: list[dict]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for payload in items:
        title = payload.get("title")
        url = payload.get("url")

        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue

        candidates.append(Candidate(**payload))
    return candidates


def _load_candidates_payload(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IntentParseError(
            f"Claude did not return valid JSON for the candidate: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise IntentParseError(
            f"Expected a JSON object for the candidate, got {type(payload).__name__}."
        )
    return payload


def _get_proposed_candidates_block(response: object) -> list[dict]:
    """Read the propose_candidates tool call, if the model made one."""
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != CANDIDATE_TOOL["name"]:
            continue
        payload = getattr(block, "input", None)
        if not isinstance(payload, dict):
            return []
        items = payload.get("candidates")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]
    return []
