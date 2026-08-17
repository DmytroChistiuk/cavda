from __future__ import annotations

import argparse
import sys

from cavda.dto.errors import AppError
from cavda.dto.models import DownloadResult
from cavda.service.confirm import confirm_with_user
from cavda.service.downloader import download, DEFAULT_OUTPUT_DIR
from cavda.service.intent_parser import parse_intent
from cavda.service.source_resolver import resolve_sources
from cavda.util.allowlist import DEFAULT_ALLOWLIST_PATH, load_allowlist
from . import __version__

__all__ = ["main"]


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
        "--prompt",
        dest="prompt",
        metavar="TEXT",
        help="What you are looking for",
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
    parser.add_argument("--version", action="version", version=f"cavda {__version__}")

    args = parser.parse_args(argv)
    args.prompt = args.prompt.strip()
    if not args.prompt:
        parser.error("Prompt not found, please use --prompt to setup it")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        allowlist = load_allowlist(args.allowlist)
        print(f"Allow-list: {', '.join(sorted(allowlist))}")

        intent = parse_intent(args.prompt)
        print(f"Looking for: {_describe(intent)}")

        candidates = resolve_sources(intent, allowlist)
        if not candidates:
            print("Claude proposed no candidates on given prompt.")
            return 1

        chosen = confirm_with_user(candidates)
        if chosen is None:
            print("Cancelled.")
            return 0

        result = download(chosen, intent, args.output_dir)
        report(result)
        return 0 if result.success else 1

    except AppError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def report(result: DownloadResult) -> None:
    """Print the outcome. yt-dlp's own error text is passed through unchanged."""
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
