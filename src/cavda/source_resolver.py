"""Claude call #2: ``UserIntent`` -> candidate URLs (plan §5.4).

This is the sensitive step, so it is constrained three ways:

1. The ``web_search`` server tool is configured with ``allowed_domains`` set to
   the loaded allow-list. The search is restricted server-side — Claude cannot
   retrieve a page outside the list in the first place.
2. The system prompt requires a citation for every candidate, and forces the
   answer through a strict tool schema so a candidate structurally cannot exist
   without a justification.
3. Locally, every returned URL is re-checked against the allow-list *and*
   against the set of URLs that actually came back in search results. A URL the
   model did not receive from a search result is dropped as fabricated.

Zero candidates, uncited candidates, off-list candidates: the resolver returns
an empty list. It never shows an unjustified guess.

Single-shot: one API call, no retry, no backoff, no caching.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit, urlunsplit

from .allowlist import domain_of, is_allowed
from .models import AppError, Candidate, UserIntent

__all__ = ["resolve_sources", "MODEL", "SYSTEM_PROMPT", "CANDIDATE_TOOL"]

MODEL = "claude-opus-5"
MAX_TOKENS = 4096
MAX_SEARCHES = 5

SYSTEM_PROMPT = """\
You find pages that a user could legally download a specific video from, using \
only the web_search tool. Your search is restricted server-side to an \
allow-list of domains; treat that list as the entire web.

Hard rules:

1. Never propose a URL you did not receive from a web_search result. Do not \
guess, complete, shorten, extend or "fix" a URL. Copy it exactly as the search \
result gave it to you. A plausible-looking URL you constructed yourself is a \
fabrication and is worse than returning nothing.
2. For every candidate, cite the specific search result you took it from: name \
the result title and quote the snippet or page text that shows this page hosts \
the requested video. "It looks like the right site" is not a citation.
3. Only propose a page if the search result gives you concrete evidence it \
contains the requested title (and season/episode, if the user gave one). If \
the evidence is about a different work, a trailer, a review, a listing page, \
or you simply cannot tell, leave it out.
4. If nothing meets these rules, call the tool with an empty candidates list. \
Returning nothing is a correct and expected outcome. Never pad the list.

When you are done searching, report your candidates by calling the \
propose_candidates tool exactly once. Do not answer in prose.
"""

CANDIDATE_TOOL = {
    "name": "propose_candidates",
    "description": (
        "Report the candidate pages found via web_search. Every candidate must "
        "quote the search result it came from. Pass an empty list if nothing "
        "qualifies."
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
                        "title_match": {
                            "type": "string",
                            "description": "What this page contains, per the search result.",
                        },
                        "justification": {
                            "type": "string",
                            "description": (
                                "The citation: which search result this came from "
                                "and the snippet showing it hosts the requested video."
                            ),
                        },
                    },
                    "required": ["url", "title_match", "justification"],
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
    """Ask Claude for candidate pages, restricted to ``allowlist``.

    # todo: exercised against the live Messages API + web_search tool before
    # first release — the offline stand-in is ``cavda.mocks.mock_resolve_sources``
    # (``--mock``).
    """
    if not allowlist:
        raise AppError("Refusing to search with an empty allow-list.")

    client = _client()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_message(intent)}],
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                # The allow-list is enforced at the API boundary, not just by us.
                "allowed_domains": sorted(allowlist),
                "max_uses": MAX_SEARCHES,
            },
            CANDIDATE_TOOL,
        ],
    )

    proposed = _proposed_candidates(response)
    retrieved = _retrieved_urls(response)
    return filter_candidates(proposed, retrieved, allowlist)


# ---------------------------------------------------------------------------
# Pure helpers — no network
# ---------------------------------------------------------------------------


def _user_message(intent: UserIntent) -> str:
    lines = [f"Title: {intent.title}"]
    if intent.season is not None:
        lines.append(f"Season: {intent.season}")
    if intent.episode is not None:
        lines.append(f"Episode: {intent.episode}")
    if intent.language:
        lines.append(f"Preferred language: {intent.language}")
    if intent.quality:
        lines.append(f"Preferred quality: {intent.quality} (informational only)")
    lines.append(
        "\nSearch the allowed domains and report pages that host this exact video."
    )
    return "\n".join(lines)


def filter_candidates(
    proposed: list[dict],
    retrieved_urls: set[str],
    allowlist: set[str],
) -> list[Candidate]:
    """Drop every candidate that is uncited, off-list, or not actually retrieved.

    ``retrieved_urls`` is the set of normalised URLs that came back inside
    ``web_search`` results. If it is empty, no search happened, so every
    candidate is a fabrication and the whole list is dropped.
    """
    kept: list[Candidate] = []
    for raw in proposed:
        url = raw.get("url")
        justification = raw.get("justification")
        title_match = raw.get("title_match")

        if not isinstance(url, str) or not url.strip():
            _drop("candidate with no URL", url)
            continue
        url = url.strip()

        if not isinstance(justification, str) or not justification.strip():
            _drop("uncited candidate", url)
            continue

        if not is_allowed(url, allowlist):
            _drop("URL outside the allow-list", url)
            continue

        if _normalise_url(url) not in retrieved_urls:
            _drop("URL not present in any search result (fabricated)", url)
            continue

        domain = domain_of(url)
        if domain is None:  # unreachable after is_allowed, kept as a guard
            _drop("unparseable URL", url)
            continue

        kept.append(
            Candidate(
                url=url,
                domain=domain,
                title_match=(title_match or "").strip() or "(no description given)",
                justification=justification.strip(),
            )
        )
    return kept


def _proposed_candidates(response: object) -> list[dict]:
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


def _retrieved_urls(response: object) -> set[str]:
    """Collect every URL that actually came back inside a web_search result."""
    urls: set[str] = set()
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None)
        if not isinstance(content, list):
            continue  # an error block, not a result list
        for item in content:
            url = getattr(item, "url", None)
            if isinstance(url, str) and url.strip():
                urls.add(_normalise_url(url))
    return urls


def _normalise_url(url: str) -> str:
    """Normalise for comparison only: lower-case host, drop fragment and trailing slash."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def _drop(reason: str, url: object) -> None:
    print(f"  dropped ({reason}): {url}", file=sys.stderr)


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AppError(
            "ANTHROPIC_API_KEY is not set. Export it for this shell session; "
            "CAVDA never reads or writes a credential file."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise AppError(
            "The 'anthropic' package is not installed. Run: pip install -e ."
        ) from exc

    return anthropic.Anthropic()
