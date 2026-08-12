"""Interactive confirmation (plan §5.6).

Prints the verified candidates and blocks until the user picks one or aborts.
Plain ``input()`` — no TUI framework. Nothing is written to disk: the choice
exists only in memory, only for this run. There is no ``--yes`` flag and no way
to skip this step; the confirmation is the point.
"""

from __future__ import annotations

import textwrap

from .models import VerifiedCandidate

__all__ = ["confirm_with_user", "format_candidate"]

_INDENT = " " * 6


def confirm_with_user(
    candidates: list[VerifiedCandidate],
) -> VerifiedCandidate | None:
    """Ask the user to pick a candidate. Returns None if they decline or abort."""
    if not candidates:
        return None

    print()
    print(f"Found {len(candidates)} verified source(s) on allowed domains:")
    print()
    for index, candidate in enumerate(candidates, start=1):
        print(format_candidate(index, candidate))

    print(
        "You are responsible for having the right to download the source you pick."
    )
    print()

    if len(candidates) == 1:
        return _confirm_single(candidates[0])
    return _choose_from_many(candidates)


def format_candidate(index: int, candidate: VerifiedCandidate) -> str:
    """Render one candidate as a numbered block."""
    content_type = candidate.content_type or "unknown"
    lines = [
        f"  [{index}] {candidate.title_match}",
        f"{_INDENT}domain:  {candidate.domain}",
        f"{_INDENT}url:     {candidate.url}",
        f"{_INDENT}checked: HTTP {candidate.http_status}, {content_type}",
        f"{_INDENT}why:",
    ]
    lines.extend(
        textwrap.wrap(
            candidate.justification,
            width=88,
            initial_indent=_INDENT + "  ",
            subsequent_indent=_INDENT + "  ",
        )
    )
    lines.append("")
    return "\n".join(lines)


def _confirm_single(candidate: VerifiedCandidate) -> VerifiedCandidate | None:
    answer = _ask("Download this source? [y/N]: ")
    if answer in ("y", "yes"):
        return candidate
    return None


def _choose_from_many(
    candidates: list[VerifiedCandidate],
) -> VerifiedCandidate | None:
    prompt = f"Pick a source [1-{len(candidates)}], or 'n' to cancel: "
    while True:
        answer = _ask(prompt)
        if answer in ("", "n", "no", "q", "quit", "abort"):
            return None
        if answer.isdigit():
            choice = int(answer)
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1]
        print(f"  Enter a number from 1 to {len(candidates)}, or 'n' to cancel.")


def _ask(prompt: str) -> str:
    """Read one answer. Ctrl-C / Ctrl-D / closed stdin all mean 'cancel'."""
    try:
        return input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "n"
