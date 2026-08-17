from __future__ import annotations

import json
from typing import Any

from cavda.dto.errors import IntentParseError
from cavda.dto.models import UserIntent

__all__ = ["parse_intent"]

from cavda.util.ai_utils import build_ai_client

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024
SYSTEM_PROMPT = """\
Extract structured search intent from a user's free-text request for a video based on schema provided.

Return only the fields of the schema, filled from user input:
<field_rules>
- title: The video/show/movie the user wants, cleaned of request-framing
  words ("find me", "can you get", "download", "please") and filler, but
  never translated, rephrased, or invented. If no recognisable title is
  present, use the full original user text verbatim as the title.
- season / episode: Integers, only when explicitly stated or unambiguously
  implied by a standard pattern (e.g. "S02E05", "season 2 episode 5", "2x05").
  Relative references like "the latest episode" or "newest season" do NOT
  count as a number — leave null. A season mentioned without an episode
  gives season a value and episode stays null (and vice versa).
- quality: The user's words normalised to one of "best", "1080p", "720p",
  "480p", "360p", "worst". Null if they did not say.
- language: an ISO 639-1 code (e.g. "en", "de", "uk") if the user asked for a
  specific language, otherwise null.
</field_rules>

<constrains>
- Never invent a title, season, episode, quality or language the user did not ask for.
- Null is always the correct answer when the user was silent about a field.
- Do not chat, explain, or add commentary — you only emit the JSON object based on provided schema.
</constrains>

<examples>
User: "find me breaking bad s2 e5 in 1080"
{"title": "Breaking Bad", "season": 2, "episode": 5, "quality": "1080p", "language": null}

User: "stranger things season 4 in ukrainian best quality"
{"title": "Stranger Things", "season": 4, "episode": null, "quality": "best", "language": "uk"}
</examples>
"""

# strict JSON-schema mode with additionalProperties=False to remove optional fields.
_NULLABLE_INT = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
_NULLABLE_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "season": _NULLABLE_INT,
        "episode": _NULLABLE_INT,
        "quality": _NULLABLE_STR,
        "language": _NULLABLE_STR,
    },
    "required": ["title", "season", "episode", "quality", "language"],
    "additionalProperties": False,
}


# todo: exercised against the live Messages API before first release
def parse_intent(prompt: str) -> UserIntent:
    """Turn the raw user prompt into a validated ``UserIntent``"""
    client = build_ai_client()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": INTENT_SCHEMA,
            },
        },
    )
    json_text = _get_content_text_block(response)
    return _convert_json_to_user_intent(json_text)


def _convert_json_to_user_intent(text: str) -> UserIntent:
    payload = _load_intent_payload(text)
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise IntentParseError("Intent JSON is missing a non-empty 'title'.")

    return UserIntent(**payload)


def _load_intent_payload(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IntentParseError(
            f"Claude did not return valid JSON for the intent: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise IntentParseError(
            f"Expected a JSON object for the intent, got {type(payload).__name__}."
        )
    return payload


def _get_content_text_block(response: object) -> str:
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "")
    raise IntentParseError("Claude's response contained no text block to parse.")
