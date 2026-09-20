"""Cut a time range with ffmpeg (H.264 + AAC for Windows players)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Compatible with Windows Media Player / most editors
COMPAT_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
COMPAT_AUDIO = ["-c:a", "aac", "-b:a", "192k"]
COMPAT_MOVFLAGS = ["-movflags", "+faststart"]


def require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "ffmpeg not found on PATH.\n"
            "  Windows (pick one):\n"
            "    winget install ffmpeg\n"
            "    choco install ffmpeg\n"
            "  Then close and reopen your terminal, and check: ffmpeg -version\n"
            "  More installs: https://ffmpeg.org/download.html"
        )
    return exe


def clip_last_seconds(
    source: Path,
    dest: Path,
    seconds: int = 30,
    *,
    start: float | None = None,
) -> Path:
    """Export a segment of `source` to `dest` as H.264/AAC.

    When `start` is None (default), export the last `seconds` via ``-sseof``.
    When `start` is set, seek to that offset (``-ss`` before ``-i``) and take
    ``seconds`` of duration (``-t``).
    """
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Re-encode (not -c copy) so cuts start on a keyframe and WMP can play them
    if start is not None:
        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            str(start),
            "-i",
            str(source),
            "-t",
            str(seconds),
            *COMPAT_VIDEO,
            *COMPAT_AUDIO,
            *COMPAT_MOVFLAGS,
            str(dest),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-sseof",
            f"-{seconds}",
            "-i",
            str(source),
            "-t",
            str(seconds),
            *COMPAT_VIDEO,
            *COMPAT_AUDIO,
            *COMPAT_MOVFLAGS,
            str(dest),
        ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest
