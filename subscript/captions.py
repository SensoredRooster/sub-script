"""Burn SRT/ASS captions onto video with ffmpeg (no Whisper / ML deps)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from subscript.clip import COMPAT_AUDIO, COMPAT_MOVFLAGS, COMPAT_VIDEO, require_ffmpeg

_DEMO_LINE = "Clip \u00b7 SUB"


def captions_enabled(cfg: dict[str, Any] | None) -> bool:
    """True unless captions.enabled is explicitly false (brand or top-level)."""
    if not cfg:
        return True
    caps = cfg.get("captions")
    if isinstance(caps, dict) and "enabled" in caps:
        return bool(caps["enabled"])
    brand = cfg.get("brand") or {}
    if isinstance(brand, dict) and "captions" in brand:
        nested = brand["captions"]
        if isinstance(nested, dict) and "enabled" in nested:
            return bool(nested["enabled"])
        if isinstance(nested, bool):
            return nested
    return True


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_demo_srt(
    path: Path,
    duration_s: float,
    *,
    text: str = _DEMO_LINE,
    segment_s: float = 2.0,
) -> Path:
    """Write simple timed placeholder captions covering ``duration_s``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, float(duration_s))
    seg = max(0.5, float(segment_s))
    blocks: list[str] = []
    idx = 1
    t = 0.0
    while t < duration - 0.05:
        end = min(t + seg, duration)
        blocks.append(
            f"{idx}\n{_srt_timestamp(t)} --> {_srt_timestamp(end)}\n{text}\n"
        )
        idx += 1
        t = end
    if not blocks:
        blocks.append(
            f"1\n{_srt_timestamp(0)} --> {_srt_timestamp(duration)}\n{text}\n"
        )
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return path


def _escape_subtitles_path(path: Path) -> str:
    """Escape an absolute path for ffmpeg ``subtitles=`` filter (Windows-safe)."""
    s = path.resolve().as_posix()
    s = s.replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    s = s.replace("[", r"\[").replace("]", r"\]")
    s = s.replace(",", r"\,")
    return s


def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return
    err = (proc.stderr or proc.stdout or "").strip()
    tail = "\n".join(err.splitlines()[-25:]) if err else "(no ffmpeg output)"
    raise RuntimeError(f"ffmpeg captions failed (exit {proc.returncode}).\n{tail}")


def burn_captions(video: Path, srt: Path, dest: Path) -> Path:
    """Burn ``srt`` onto ``video`` via ffmpeg subtitles filter \u2192 ``dest``."""
    ffmpeg = require_ffmpeg()
    video = Path(video)
    srt = Path(srt)
    dest = Path(dest)
    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")
    if not srt.exists():
        raise FileNotFoundError(f"srt not found: {srt}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    sub_path = _escape_subtitles_path(srt)
    style = (
        "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=80"
    )
    vf = f"subtitles={sub_path}:force_style='{style}'"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vf",
        vf,
        *COMPAT_VIDEO,
        *COMPAT_AUDIO,
        *COMPAT_MOVFLAGS,
        str(dest),
    ]
    try:
        _run_ffmpeg(cmd)
        return dest
    except RuntimeError:
        vf_plain = f"subtitles={sub_path}"
        cmd_plain = [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-vf",
            vf_plain,
            *COMPAT_VIDEO,
            *COMPAT_AUDIO,
            *COMPAT_MOVFLAGS,
            str(dest),
        ]
        _run_ffmpeg(cmd_plain)
        return dest


def probe_duration_seconds(video: Path) -> float:
    """Best-effort duration via ffprobe; falls back to 30s."""
    ffprobe = require_ffmpeg().replace("ffmpeg", "ffprobe")
    if not Path(ffprobe).exists() and "ffmpeg" in require_ffmpeg():
        import shutil

        ffprobe = shutil.which("ffprobe") or ffprobe
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            val = float((proc.stdout or "").strip())
            if val > 0:
                return val
    except Exception:
        pass
    return 30.0


def maybe_caption_vertical(
    vertical: Path,
    out_dir: Path,
    stamp: str,
    cfg: dict[str, Any],
    *,
    duration_s: float | None = None,
) -> Path | None:
    """If captions enabled, write demo SRT and burn onto vertical \u2192 captioned path."""
    if not captions_enabled(cfg):
        return None
    vertical = Path(vertical)
    if not vertical.exists():
        return None
    dur = float(duration_s) if duration_s is not None else probe_duration_seconds(vertical)
    srt = out_dir / f"clip-captions-{stamp}.srt"
    write_demo_srt(srt, dur)
    dest = out_dir / f"clip-vertical-captioned-{stamp}.mp4"
    try:
        return burn_captions(vertical, srt, dest)
    except RuntimeError as exc:
        print(f"Caption burn skipped: {exc}")
        return None
