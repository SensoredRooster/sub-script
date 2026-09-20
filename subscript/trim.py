"""Trim a clip to a start/end window (H.264 + AAC)."""

from __future__ import annotations

from pathlib import Path

from subscript.clip import (
    COMPAT_AUDIO,
    COMPAT_MOVFLAGS,
    COMPAT_VIDEO,
    require_ffmpeg,
    run_ffmpeg,
)


def trim_clip(source: Path, dest: Path, start: float, end: float) -> Path:
    """Re-encode ``source`` from ``start`` to ``end`` seconds into ``dest``."""
    start = float(start)
    end = float(end)
    if start < 0:
        raise ValueError("start must be 0 or greater")
    if end <= start:
        raise ValueError("end must be greater than start")
    source = Path(source)
    dest = Path(dest)
    if not source.is_file():
        raise FileNotFoundError(f"Source clip not found: {source}")
    if source.resolve() == dest.resolve():
        raise ValueError("trim destination must differ from the source file")
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
    run_ffmpeg(cmd, what="ffmpeg trim")
    return dest
