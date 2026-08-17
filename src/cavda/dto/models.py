from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "UserIntent",
    "Candidate",
    "DownloadResult"
]


@dataclass(frozen=True)
class UserIntent:
    """Structured form of the user's prompt."""

    title: str
    season: Optional[int]
    episode: Optional[int]
    quality: Optional[str]
    language: Optional[str]


@dataclass(frozen=True)
class Candidate:
    """A URL Claude video content propose"""

    url: str
    title: str
    description: Optional[str]


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of the single yt-dlp invocation."""

    success: bool
    output_path: Optional[str]
    error_message: Optional[str]
