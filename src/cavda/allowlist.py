"""Allow-list loading and matching (plan §5.2).

``allowlist.yaml`` is the single source of truth for which domains CAVDA will
ever treat as legitimate. Matching is done on the parsed netloc — exact host or
true subdomain — never as a substring, so ``evil-archive.org.attacker.com`` and
``archive.org.evil.com`` are both rejected.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .models import AppError

__all__ = ["load_allowlist", "is_allowed", "domain_of", "DEFAULT_ALLOWLIST_PATH"]

DEFAULT_ALLOWLIST_PATH = "allowlist.yaml"

# Only these schemes are ever considered. No file://, no ftp://, no data:.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def load_allowlist(path: str = DEFAULT_ALLOWLIST_PATH) -> set[str]:
    """Read the YAML allow-list and return a normalised set of domains.

    Raises ``AppError`` if the file is missing, unreadable, malformed, or empty.
    An empty allow-list is an error rather than an implicit "allow nothing"
    because a silently empty list looks like a working app that finds nothing.
    """
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise AppError(
            f"Allow-list not found at {file_path}. "
            "CAVDA only searches domains you have explicitly listed; "
            "create the file or pass --allowlist /path/to/allowlist.yaml."
        )

    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AppError(f"Could not read allow-list {file_path}: {exc}") from exc

    if not isinstance(raw, dict) or "domains" not in raw:
        raise AppError(
            f"{file_path} must be a YAML mapping with a top-level 'domains:' list."
        )

    entries = raw["domains"]
    if not isinstance(entries, list):
        raise AppError(f"{file_path}: 'domains' must be a list of domain strings.")

    domains: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry.strip():
            raise AppError(
                f"{file_path}: every entry under 'domains' must be a non-empty string, "
                f"got {entry!r}."
            )
        domains.add(_normalise_domain(entry))

    if not domains:
        raise AppError(f"{file_path} lists no domains — there is nothing to search.")

    return domains


def is_allowed(url: str, allowlist: set[str]) -> bool:
    """True if ``url``'s host is an allow-listed domain or a subdomain of one."""
    host = domain_of(url)
    if host is None:
        return False
    return any(host == d or host.endswith("." + d) for d in allowlist)


def domain_of(url: str) -> str | None:
    """Return the normalised host of an http(s) URL, or None if it is unusable.

    Strips userinfo, port and the trailing root dot, and lower-cases the host.
    A URL carrying userinfo (``https://user:pw@host/``) is rejected outright —
    that is a credential in a URL, which this app does not handle.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None

    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return None
    if "@" in parts.netloc:  # userinfo — never accepted
        return None

    try:
        host = parts.hostname
    except ValueError:
        return None
    if not host:
        return None

    return _normalise_domain(host)


def _normalise_domain(domain: str) -> str:
    return domain.strip().strip(".").lower()
