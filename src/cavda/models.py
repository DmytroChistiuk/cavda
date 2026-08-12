"""Shared dataclasses and the application exception hierarchy (plan §5.1, §8).

Frozen dataclasses: no accidental mutation, cheap to reason about, and no
persistence temptation — these objects live only for the duration of one run.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "UserIntent",
    "Candidate",
    "VerifiedCandidate",
    "DownloadResult",
    "AppError",
    "IntentParseError",
    "NoVerifiedCandidatesError",
    "DownloadFailedError",
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserIntent:
    """Structured form of the user's free-text prompt."""

    title: str
    season: int | None
    episode: int | None
    quality: str | None  # e.g. "1080p", "best"
    language: str | None


@dataclass(frozen=True)
class Candidate:
    """A URL Claude proposes, before the app has verified anything itself."""

    url: str
    domain: str
    title_match: str  # what Claude thinks this page contains
    justification: str  # why Claude picked it (must cite the search result)


@dataclass(frozen=True)
class VerifiedCandidate(Candidate):
    """A candidate that survived the local allow-list re-check and a live HTTP probe."""

    http_status: int
    content_type: str | None


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of the single yt-dlp invocation."""

    success: bool
    output_path: str | None
    error_message: str | None


# ---------------------------------------------------------------------------
# Errors (plan §8)
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base class for every error CAVDA raises deliberately.

    ``main()`` catches these, prints ``Error: <message>`` and exits 1. Anything
    else is a bug and is allowed to bubble up with a full traceback.
    """


class IntentParseError(AppError):
    """Claude returned something that is not a valid ``UserIntent``."""


class NoVerifiedCandidatesError(AppError):
    """Nothing on an allowed domain could be verified as reachable."""


class DownloadFailedError(AppError):
    """The yt-dlp invocation could not be built or could not be started."""
