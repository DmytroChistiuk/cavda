"""Offline stand-ins for the three impure boundaries, used by ``--mock``.

Every function marked ``# todo`` in ``intent_parser``, ``source_resolver``,
``verifier`` and ``downloader`` needs a live service to exercise: the Anthropic
API, real hosts, a real yt-dlp binary. This module provides deterministic
substitutes so the pipeline can be run end to end with no API key, no network
and no downloads.

The mocks obey the same constraints as the real code — they honour the
allow-list, drop uncited candidates, and never fabricate a success. They are
development aids, not a degraded mode: ``--mock`` never downloads anything.
"""

from __future__ import annotations

import re

from .allowlist import domain_of, is_allowed
from .models import (
    Candidate,
    DownloadResult,
    IntentParseError,
    UserIntent,
    VerifiedCandidate,
)

__all__ = [
    "mock_parse_intent",
    "mock_resolve_sources",
    "mock_verify",
    "mock_download",
]

_SEASON_EPISODE_RE = re.compile(
    r"\b(?:s(?:eason)?\s*)(\d{1,2})\D{0,10}?(?:e(?:pisode)?\s*)(\d{1,3})\b",
    re.IGNORECASE,
)
_COMPACT_SE_RE = re.compile(r"\bs(\d{1,2})e(\d{1,3})\b", re.IGNORECASE)
_QUALITY_RE = re.compile(r"\b(\d{3,4})p\b|\b(best|worst|audio)\b", re.IGNORECASE)
_LANGUAGES = {
    "english": "en",
    "german": "de",
    "french": "fr",
    "spanish": "es",
    "ukrainian": "uk",
    "polish": "pl",
    "italian": "it",
}


def mock_parse_intent(prompt: str) -> UserIntent:
    """Regex stand-in for Claude call #1. Same contract, no API key needed."""
    text = prompt.strip()
    if not text:
        raise IntentParseError("Empty prompt — nothing to parse.")

    season = episode = None
    match = _COMPACT_SE_RE.search(text) or _SEASON_EPISODE_RE.search(text)
    if match:
        season, episode = int(match.group(1)), int(match.group(2))

    quality = None
    quality_match = _QUALITY_RE.search(text)
    if quality_match:
        height, keyword = quality_match.group(1), quality_match.group(2)
        quality = f"{height}p" if height else keyword.lower()

    language = next(
        (code for name, code in _LANGUAGES.items() if name in text.lower()), None
    )

    # Strip the bits we just consumed so the title is not polluted by them.
    title = text
    for pattern in (_COMPACT_SE_RE, _SEASON_EPISODE_RE, _QUALITY_RE):
        title = pattern.sub(" ", title)
    title = re.sub(r"\b(in|download|please|the video|episode|season)\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\s{2,}", " ", title).strip(" ,-–—") or text

    return UserIntent(
        title=title,
        season=season,
        episode=episode,
        quality=quality,
        language=language,
    )


def mock_resolve_sources(intent: UserIntent, allowlist: set[str]) -> list[Candidate]:
    """Stand-in for Claude call #2. Invents one candidate per allowed domain.

    Still honours the allow-list, and still labels every candidate with an
    explicit justification — here, one that says plainly that it is fabricated,
    so a mock run can never be mistaken for a real search result.
    """
    label = intent.title
    if intent.season is not None and intent.episode is not None:
        label = f"{label} S{intent.season:02d}E{intent.episode:02d}"

    candidates: list[Candidate] = []
    for domain in sorted(allowlist):
        url = f"https://{domain}/details/{_slug(label)}"
        if not is_allowed(url, allowlist):  # guard, should never trigger
            continue
        candidates.append(
            Candidate(
                url=url,
                domain=domain_of(url) or domain,
                title_match=f"{label} (mock result)",
                justification=(
                    "MOCK DATA — no web search was performed. This URL was "
                    f"generated from the allow-list entry '{domain}' and almost "
                    "certainly does not exist."
                ),
            )
        )
    return candidates


def mock_verify(
    candidate: Candidate,
    allowlist: set[str],
    timeout: float = 0.0,
) -> VerifiedCandidate | None:
    """Stand-in for the HTTP probe. No request is made; the allow-list still applies."""
    del timeout  # no network call to time out
    if not is_allowed(candidate.url, allowlist):
        return None
    return VerifiedCandidate(
        url=candidate.url,
        domain=candidate.domain,
        title_match=candidate.title_match,
        justification=candidate.justification,
        http_status=200,
        content_type="text/html (mock — not fetched)",
    )


def mock_download(
    candidate: Candidate,
    intent: UserIntent,
    output_dir: str = "downloads",
) -> DownloadResult:
    """Stand-in for the yt-dlp run. Prints the command it *would* run, then stops."""
    from .downloader import build_command

    cmd = build_command(candidate, intent, output_dir)
    print()
    print("Would run:", " ".join(cmd))
    print()
    return DownloadResult(
        success=False,
        output_path=None,
        error_message="Mock mode: no download was attempted.",
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unknown"
