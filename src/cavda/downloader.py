"""The yt-dlp boundary (plan §5.7).

The command is built as an argument list and handed to ``subprocess.run``
without a shell, so nothing in a URL or title can be interpreted as shell
syntax.

What this module structurally cannot do: there is no code path that adds
cookies, auth headers, credentials, ``--no-check-certificate``, a proxy, a
geo-bypass flag, or ``--allow-unplayable-formats``. ``build_command`` asserts
that none of those appear in the final argument list, so a future edit that
tries to add one fails loudly instead of quietly shipping.

yt-dlp's own stderr is surfaced verbatim. If it says "This video is DRM
protected" or "Sign in to confirm your age", that text is what the user sees —
the app adds no interpretation that could imply a workaround exists, and never
re-runs the command with different flags.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .models import Candidate, DownloadFailedError, DownloadResult, UserIntent

__all__ = [
    "download",
    "build_command",
    "format_selector_for",
    "DEFAULT_OUTPUT_DIR",
    "FORBIDDEN_ARGS",
]

DEFAULT_OUTPUT_DIR = "downloads"
OUTPUT_TEMPLATE = "%(title)s.%(ext)s"

# Arguments this app must never emit. Enforced in build_command, not just docs.
FORBIDDEN_ARGS = frozenset(
    {
        "--cookies",
        "--cookies-from-browser",
        "--no-check-certificate",
        "--username",
        "--password",
        "--twofactor",
        "--netrc",
        "--netrc-cmd",
        "--netrc-location",
        "--video-password",
        "--ap-mso",
        "--ap-username",
        "--ap-password",
        "--client-certificate",
        "--client-certificate-key",
        "--client-certificate-password",
        "--add-header",
        "--headers",
        "--referer",
        "--proxy",
        "--geo-verification-proxy",
        "--geo-bypass",
        "--geo-bypass-country",
        "--geo-bypass-ip-block",
        "--xff",
        "--allow-unplayable-formats",
        "--exec",
        "--exec-before-download",
    }
)

_QUALITY_FORMATS = {
    "best": "bestvideo*+bestaudio/best",
    "worst": "worstvideo*+worstaudio/worst",
    "audio": "bestaudio/best",
}
_HEIGHT_RE = re.compile(r"^(\d{3,4})p?$", re.IGNORECASE)


def format_selector_for(quality: str | None) -> str:
    """Map ``UserIntent.quality`` to a yt-dlp format string.

    Unrecognised values fall back to "best" with a warning on stderr — noisy,
    not silent.
    """
    if not quality:
        return _QUALITY_FORMATS["best"]

    normalised = quality.strip().lower()
    if normalised in _QUALITY_FORMATS:
        return _QUALITY_FORMATS[normalised]

    match = _HEIGHT_RE.match(normalised)
    if match:
        height = int(match.group(1))
        return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"

    print(
        f"Warning: unrecognised quality {quality!r}; using best available instead.",
        file=sys.stderr,
    )
    return _QUALITY_FORMATS["best"]


def build_command(
    candidate: Candidate,
    intent: UserIntent,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> list[str]:
    """Build the yt-dlp argument list. Never a shell string."""
    output_template = str(Path(output_dir) / OUTPUT_TEMPLATE)
    cmd = [
        "yt-dlp",
        "-f",
        format_selector_for(intent.quality),
        "-o",
        output_template,
        "--no-playlist",
        "--",  # everything after this is a URL, never an option
        candidate.url,
    ]

    # Structural guarantee, checked on every single invocation.
    offenders = sorted(FORBIDDEN_ARGS.intersection(cmd))
    if offenders:
        raise DownloadFailedError(
            f"Refusing to run yt-dlp with prohibited arguments: {offenders}. "
            "CAVDA does not bypass authentication, DRM, geo-blocks or TLS checks."
        )

    return cmd


def download(
    candidate: Candidate,
    intent: UserIntent,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> DownloadResult:
    """Run yt-dlp once on the confirmed URL and report what happened.

    # todo: exercised against a real yt-dlp binary before first release — the
    # offline stand-in is ``cavda.mocks.mock_download`` (``--mock``).
    """
    cmd = build_command(candidate, intent, output_dir)

    destination = Path(output_dir)
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadFailedError(f"Cannot create output directory {destination}: {exc}") from exc

    print()
    print("Running:", " ".join(cmd))
    print()

    try:
        # stdout is inherited so yt-dlp's own progress bar prints live.
        # stderr is captured so its error text can be surfaced verbatim below.
        completed = subprocess.run(
            cmd,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DownloadFailedError(
            "yt-dlp was not found on PATH. Install it (pip install yt-dlp) and retry."
        ) from exc
    except OSError as exc:
        raise DownloadFailedError(f"Could not start yt-dlp: {exc}") from exc

    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        # Surface yt-dlp's own words. No interpretation, no suggested workaround,
        # no second attempt with different flags.
        if stderr:
            print(stderr, file=sys.stderr)
        tail = "\n".join(stderr.splitlines()[-10:]) if stderr else ""
        message = tail or f"yt-dlp exited with code {completed.returncode}."
        return DownloadResult(success=False, output_path=None, error_message=message)

    if stderr:  # warnings on a successful run are still worth showing
        print(stderr, file=sys.stderr)

    return DownloadResult(
        success=True,
        output_path=str(destination.resolve()),
        error_message=None,
    )
