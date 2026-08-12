"""Orchestration only (plan §5.8).

``main()`` is the architecture diagram in code form: five linear stages, no
framework magic, readable top to bottom. It catches ``AppError`` subclasses and
prints a clean message; anything else bubbles up with a full traceback, because
a bug should not be mistaken for a handled failure.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .allowlist import DEFAULT_ALLOWLIST_PATH, load_allowlist
from .confirm import confirm_with_user
from .downloader import DEFAULT_OUTPUT_DIR
from .models import AppError, DownloadResult

__all__ = ["main", "parse_args", "report"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cavda",
        description=(
            "CAVDA — CLI AI Video Downloader App. Finds a video on domains you "
            "have explicitly allow-listed, asks you to confirm, then hands the "
            "URL to yt-dlp. Stateless: nothing is saved between runs."
        ),
        epilog=(
            "CAVDA never bypasses DRM, paywalls, geo-blocks or authentication, "
            "and never stores credentials. You are responsible for having the "
            "right to download what you ask for."
        ),
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help='What you are looking for, e.g. "Night of the Living Dead 1968 in 1080p".',
    )
    parser.add_argument(
        "--prompt",
        dest="prompt_flag",
        metavar="TEXT",
        help="Same as the positional argument.",
    )
    parser.add_argument(
        "--allowlist",
        default=DEFAULT_ALLOWLIST_PATH,
        metavar="PATH",
        help=f"Path to the allow-list YAML (default: {DEFAULT_ALLOWLIST_PATH}).",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Where yt-dlp writes the file (default: ./{DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Run the pipeline with offline stand-ins for the Claude, HTTP and "
            "yt-dlp calls. No API key, no network, no download."
        ),
    )
    parser.add_argument("--version", action="version", version=f"cavda {__version__}")

    args = parser.parse_args(argv)
    args.prompt = args.prompt or args.prompt_flag
    if not args.prompt or not args.prompt.strip():
        parser.error("give a prompt, either positionally or with --prompt")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.mock:
        from .mocks import mock_download as download
        from .mocks import mock_parse_intent as parse_intent
        from .mocks import mock_resolve_sources as resolve_sources
        from .mocks import mock_verify as verify

        print("[mock mode] no API calls, no HTTP requests, no downloads.\n")
    else:
        from .downloader import download
        from .intent_parser import parse_intent
        from .source_resolver import resolve_sources
        from .verifier import verify

    try:
        allowlist = load_allowlist(args.allowlist)
        print(f"Allow-list: {', '.join(sorted(allowlist))}")

        intent = parse_intent(args.prompt)  # 5.3
        print(f"Looking for: {_describe(intent)}")

        candidates = resolve_sources(intent, allowlist)  # 5.4
        if not candidates:
            print("Claude proposed no cited candidates on allowed domains.")
            return 1

        print(f"Verifying {len(candidates)} candidate(s)...")
        verified = [v for c in candidates if (v := verify(c, allowlist))]  # 5.5
        if not verified:
            print("No verifiable sources found on allowed domains.")
            return 1

        chosen = confirm_with_user(verified)  # 5.6
        if chosen is None:
            print("Cancelled.")
            return 0

        result = download(chosen, intent, args.output_dir)  # 5.7
        report(result)
        return 0 if result.success else 1

    except AppError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def report(result: DownloadResult) -> None:
    """Print the outcome. yt-dlp's own error text is passed through unchanged."""
    print()
    if result.success:
        print(f"Done. Saved to: {result.output_path}")
    else:
        print("Download failed. yt-dlp reported:", file=sys.stderr)
        print(result.error_message or "(no error output)", file=sys.stderr)


def _describe(intent) -> str:
    parts = [intent.title]
    if intent.season is not None and intent.episode is not None:
        parts.append(f"S{intent.season:02d}E{intent.episode:02d}")
    elif intent.season is not None:
        parts.append(f"season {intent.season}")
    if intent.quality:
        parts.append(f"[{intent.quality}]")
    if intent.language:
        parts.append(f"[lang={intent.language}]")
    return " ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
