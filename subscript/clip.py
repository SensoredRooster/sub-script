"""Cut the last N seconds with ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH — install ffmpeg first")
    return exe


def clip_last_seconds(
    source: Path,
    dest: Path,
    seconds: int = 30,
) -> Path:
    """Export the last `seconds` of `source` to `dest`."""
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    # -sseof seeks from end; -t limits duration
    cmd = [
        ffmpeg,
        "-y",
        "-sseof",
        f"-{seconds}",
        "-i",
        str(source),
        "-t",
        str(seconds),
        "-c",
        "copy",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest
