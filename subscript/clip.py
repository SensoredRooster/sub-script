"""Cut a time range with ffmpeg (H.264 + AAC for Windows players)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from subscript.runtime_paths import ffmpeg_install_hint, find_ffmpeg

# Compatible with Windows Media Player / most editors
COMPAT_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
COMPAT_AUDIO = ["-c:a", "aac", "-b:a", "192k"]
COMPAT_MOVFLAGS = ["-movflags", "+faststart"]


def require_ffmpeg() -> str:
    """Return path to ffmpeg — prefer beside the app (onedir), then PATH."""
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError(ffmpeg_install_hint())
    return exe


def run_ffmpeg(cmd: list[str], what: str = "ffmpeg") -> None:
    """Run an ffmpeg command; on failure raise RuntimeError with the last stderr lines.

    Decodes output as UTF-8 with replacement so odd bytes in file names can never
    turn a clear ffmpeg error into a UnicodeDecodeError.
    """
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode == 0:
        return
    err = (proc.stderr or proc.stdout or "").strip()
    tail = "\n".join(err.splitlines()[-20:]) if err else "(no ffmpeg output)"
    raise RuntimeError(f"{what} failed (exit {proc.returncode}).\n{tail}")


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
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")
    seconds = max(1, int(seconds))
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
    run_ffmpeg(cmd, what="ffmpeg clip")
    return dest
