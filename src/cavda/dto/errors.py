__all__ = [
    "AppError",
    "IntentParseError",
    "NoVerifiedCandidatesError",
    "DownloadFailedError"
]


class AppError(Exception):
    """Base class for every application errors"""


class IntentParseError(AppError):
    """Claude returned something that is not a valid ``UserIntent``."""


class NoVerifiedCandidatesError(AppError):
    """Nothing on an allowed domain could be verified as reachable."""


class DownloadFailedError(AppError):
    """The yt-dlp invocation could not be built or could not be started."""
