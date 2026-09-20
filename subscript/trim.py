"""Trim a clip to a start/end window (H.264 + AAC)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from subscript.clip import COMPAT_AUDIO, COMPAT_MOVFLAGS, COMPAT_VIDEO, require_ffmpeg


def trim_clip(source: Path, dest: Path, start: float, end: float) -> Path:
    if end <= start:
        raise ValueError("end must be greater than start")
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = end - start
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-i",
        str(source),
        "-t",
        str(duration),
        *COMPAT_VIDEO,
        *COMPAT_AUDIO,
        *COMPAT_MOVFLAGS,
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest
