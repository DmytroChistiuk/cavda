"""Claude call #1: free-text prompt -> ``UserIntent`` (plan §5.3).

Uses the Messages API with a JSON-schema structured output so the model cannot
answer in prose. The JSON is still validated against the dataclass shape in
code before ``UserIntent`` is constructed — the schema is a convenience, not a
guarantee we lean on. Malformed output raises ``IntentParseError``.

Single-shot: one API call, no retry, no backoff, no caching. If it fails, the
run ends.
"""

from __future__ import annotations

import json
import os

from .models import AppError, IntentParseError, UserIntent

__all__ = ["parse_intent", "MODEL", "INTENT_SCHEMA", "SYSTEM_PROMPT"]

MODEL = "claude-opus-5"
MAX_TOKENS = 1024

SYSTEM_PROMPT = """\
You extract structured search intent from a user's free-text request for a video.

Return only the fields of the schema, filled from what the user actually wrote:

- title: the work the user is asking for, cleaned up but not invented. If they
  gave no recognisable title, use the prompt text itself rather than guessing.
- season / episode: integers, only when the user clearly indicated them
  (e.g. "S02E05", "season 2 episode 5"). Otherwise null.
- quality: the user's words normalised to one of "best", "1080p", "720p",
  "480p", "360p", "audio", or "worst". Null if they did not say.
- language: an ISO 639-1 code (e.g. "en", "de", "uk") if the user asked for a
  specific language, otherwise null.

Never invent a season, episode, quality or language the user did not ask for.
Null is always the correct answer when the user was silent about a field.
"""

# anyOf rather than {"type": ["integer", "null"]} — broadest schema support.
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


def parse_intent(prompt: str) -> UserIntent:
    """Turn the raw user prompt into a validated ``UserIntent``.

    # todo: exercised against the live Messages API before first release —
    # the offline stand-in is ``cavda.mocks.mock_parse_intent`` (``--mock``).
    """
    prompt = prompt.strip()
    if not prompt:
        raise IntentParseError("Empty prompt — nothing to parse.")

    client = _client()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "effort": "low",
            "format": {
                "type": "json_schema",
                "schema": INTENT_SCHEMA,
            },
        },
    )

    return _intent_from_response_text(_first_text_block(response))


# ---------------------------------------------------------------------------
# Pure helpers — no network, easy to reason about and to test
# ---------------------------------------------------------------------------


def _intent_from_response_text(text: str) -> UserIntent:
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

    unexpected = set(payload) - set(INTENT_SCHEMA["properties"])
    if unexpected:
        raise IntentParseError(
            f"Intent JSON contains unexpected fields: {sorted(unexpected)}."
        )

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise IntentParseError("Intent JSON is missing a non-empty 'title'.")

    return UserIntent(
        title=title.strip(),
        season=_optional_int(payload.get("season"), "season"),
        episode=_optional_int(payload.get("episode"), "episode"),
        quality=_optional_str(payload.get("quality"), "quality"),
        language=_optional_str(payload.get("language"), "language"),
    )


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    # bool is an int subclass; it is never a valid season/episode.
    if isinstance(value, bool) or not isinstance(value, int):
        raise IntentParseError(f"Intent field '{field}' must be an integer or null.")
    if value < 0:
        raise IntentParseError(f"Intent field '{field}' must not be negative.")
    return value


def _optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise IntentParseError(f"Intent field '{field}' must be a string or null.")
    stripped = value.strip()
    return stripped or None


def _first_text_block(response: object) -> str:
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "")
    raise IntentParseError("Claude's response contained no text block to parse.")


def _client():
    """Build an SDK client. The key is read from the environment and never stored."""
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
