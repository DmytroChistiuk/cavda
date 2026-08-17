import re
from pathlib import Path
from typing import Optional

import yt_dlp

from cavda.dto.models import UserIntent, DownloadResult, Candidate

DEFAULT_OUTPUT_DIR = "downloads"

__all__ = ["download", "DEFAULT_OUTPUT_DIR"]


def download(
        candidate: Candidate,
        intent: UserIntent,
        output_dir: str = DEFAULT_OUTPUT_DIR,
) -> DownloadResult:
    """Run yt-dlp to download the confirmed content."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_template = _build_output_template(intent, output_dir)
    format_selector = _build_quality_format_selector(intent)

    ydl_opts = {
        "format": format_selector,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
    }

    if intent.language:
        ydl_opts.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [intent.language, f"{intent.language}.*"],
                "embedsubtitles": True,
            }
        )
        ydl_opts["format"] = f"bv*+ba[language={intent.language}]/{format_selector}"
        ydl_opts["format_sort"] = [f"lang:{intent.language}"]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(candidate.url, download=True)
            requested = (info or {}).get("requested_downloads") or []
            if requested and requested[0].get("filepath"):
                destination_str = requested[0]["filepath"]
            else:
                destination_str = ydl.prepare_filename(info)

        destination = Path(destination_str)

        if not destination.exists():
            return DownloadResult(
                success=False,
                output_path=None,
                error_message=(
                    f"yt-dlp reported completion but file not found at "
                    f"{destination}"
                ),
            )

        return DownloadResult(
            success=True,
            output_path=str(destination.resolve()),
            error_message=None,
        )

    except yt_dlp.utils.DownloadError as e:
        return DownloadResult(
            success=False,
            output_path=None,
            error_message=f"Download failed: {e}",
        )


def _build_output_template(intent: UserIntent, output_dir: str) -> str:
    """Build a filesystem name for content"""
    parts = [intent.title]

    if intent.season is not None:
        parts.append(f"-S{intent.season}")

    if intent.episode is not None:
        parts.append(f"E{intent.episode}")

    filename = "".join(parts) + ".%(ext)s"
    return str(Path(output_dir) / filename)


def _build_quality_format_selector(intent: UserIntent) -> str:
    height = _get_height_from_quality(intent.quality)
    if height:
        return (
            f"bv*[height<={height}]+ba/b[height<={height}]"
            f"/bv*+ba/b"  # fallback if nothing matches
        )
    return "bv*+ba/b"


def _get_height_from_quality(quality: Optional[str]) -> Optional[int]:
    """Parse '1080p', '720p', etc. into a pixel height."""
    if not quality:
        return None
    match = re.search(r"(\d+)", quality)
    return int(match.group(1)) if match else None
