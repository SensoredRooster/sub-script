from __future__ import annotations

import subprocess
from pathlib import Path

from subscript.clip import require_ffmpeg


def trim_clip(source: Path, dest: Path, start: float, end: float) -> Path:
    if end <= start:
        raise ValueError("end must be greater than start")
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = end - start
    cmd = [
        ffmpeg, "-y",
        "-ss", str(start),
        "-i", str(source),
        "-t", str(duration),
        "-c", "copy",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest
