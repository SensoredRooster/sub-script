"""Cut the last N seconds with ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# WMP-friendly Shorts export: H.264 + AAC (not stream-copy / HEVC).
H264_ENCODE_ARGS = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "20",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-movflags",
    "+faststart",
]


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
) -> Path:
    """Export the last `seconds` of `source` to `dest`."""
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    # -sseof seeks from end; -t limits duration. Re-encode so cuts are not
    # mid-GOP and HEVC game replays play in Windows Media Player.
    cmd = [
        ffmpeg,
        "-y",
        "-sseof",
        f"-{seconds}",
        "-i",
        str(source),
        "-t",
        str(seconds),
        *H264_ENCODE_ARGS,
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest
