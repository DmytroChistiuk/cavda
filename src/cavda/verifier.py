"""Deterministic verification — no AI (plan §5.5).

For each candidate:
  (a) re-check the allow-list locally (defence in depth: never trust the fact
      that the AI call was domain-restricted),
  (b) issue a single HEAD (falling back to GET once, as the plan specifies)
      with a short timeout,
  (c) require an HTTP 2xx and a plausible content-type,
  (d) re-check the allow-list on the *final* URL, so a redirect cannot walk the
      candidate off the list.

No retry: one failed check drops the candidate, it is not re-attempted. No
cookies are sent or stored, no auth headers are attached, TLS verification is
never disabled.
"""

from __future__ import annotations

import sys

from .allowlist import is_allowed
from .models import Candidate, VerifiedCandidate

__all__ = ["verify", "DEFAULT_TIMEOUT", "PLAUSIBLE_CONTENT_TYPES"]

DEFAULT_TIMEOUT = 10.0  # seconds, whole request
MAX_REDIRECTS = 5

_USER_AGENT = "cavda/0.1 (+https://example.invalid/cavda)"

# A page that could plausibly hold a video, or a media/manifest response itself.
PLAUSIBLE_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "video/",
    "audio/",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/dash+xml",
    "application/octet-stream",
)


def verify(
    candidate: Candidate,
    allowlist: set[str],
    timeout: float = DEFAULT_TIMEOUT,
) -> VerifiedCandidate | None:
    """Return a ``VerifiedCandidate``, or None if the candidate is dropped.

    # todo: exercised against real hosts before first release — the offline
    # stand-in is ``cavda.mocks.mock_verify`` (``--mock``).
    """
    # (a) Defence in depth: the resolver already checked this. Check again.
    if not is_allowed(candidate.url, allowlist):
        _drop(candidate, "not on the allow-list")
        return None

    import httpx

    # A fresh client per candidate, with no cookie jar carried between them.
    # verify=True is the httpx default and is never overridden.
    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = client.head(candidate.url)
            # (b) Single GET fallback for hosts that do not answer HEAD.
            if response.status_code in (403, 405, 501) or response.status_code >= 500:
                response = client.get(candidate.url)
    except httpx.HTTPError as exc:
        _drop(candidate, f"request failed ({type(exc).__name__}: {exc})")
        return None

    # (d) A redirect must not carry us off the allow-list.
    final_url = str(response.url)
    if not is_allowed(final_url, allowlist):
        _drop(candidate, f"redirected off the allow-list to {final_url}")
        return None

    # (c) 2xx only.
    if not 200 <= response.status_code < 300:
        _drop(candidate, f"HTTP {response.status_code}")
        return None

    content_type = response.headers.get("content-type")
    if not _is_plausible(content_type):
        _drop(candidate, f"implausible content-type {content_type!r}")
        return None

    return VerifiedCandidate(
        url=candidate.url,
        domain=candidate.domain,
        title_match=candidate.title_match,
        justification=candidate.justification,
        http_status=response.status_code,
        content_type=content_type,
    )


def _is_plausible(content_type: str | None) -> bool:
    if not content_type:
        return False
    value = content_type.split(";", 1)[0].strip().lower()
    return any(value.startswith(prefix) for prefix in PLAUSIBLE_CONTENT_TYPES)


def _drop(candidate: Candidate, reason: str) -> None:
    print(f"  dropped ({reason}): {candidate.url}", file=sys.stderr)
