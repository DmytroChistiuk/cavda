from __future__ import annotations

from cavda.dto.models import Candidate

__all__ = ["confirm_with_user"]

_INDENT = " " * 6


def confirm_with_user(candidates: list[Candidate]) -> Candidate | None:
    """Ask the user to pick a candidate. Returns None if they decline or abort."""
    print(f"Found {len(candidates)} on allowed domains:")
    for index, candidate in enumerate(candidates, start=1):
        print(format_candidate(index, candidate))

    print("You are responsible for having the right to download the source you pick.")

    if len(candidates) == 1:
        return _confirm_single(candidates[0])
    return _choose_from_many(candidates)


def format_candidate(index: int, candidate: Candidate) -> str:
    """Render one candidate as a block."""
    lines = [
        f"  [{index}] {candidate.title}",
        f"{_INDENT}description: HTTP {candidate.description}",
        f"{_INDENT}url:     {candidate.url}"
    ]
    return "\n".join(lines)


def _confirm_single(candidate: Candidate) -> Candidate | None:
    answer = _ask("Download this source? [y/n]: ")
    if answer in ("y", "yes"):
        return candidate
    return None


def _choose_from_many(candidates: list[Candidate]) -> Candidate | None:
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
