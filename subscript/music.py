"""Optional low-volume music bed mixed under clip audio (ffmpeg amix)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from subscript.clip import COMPAT_AUDIO, COMPAT_MOVFLAGS, COMPAT_VIDEO, require_ffmpeg
from subscript.runtime_paths import app_dir

ROOT = app_dir()

DEFAULT_MUSIC_REL = "assets/music.mp3"
# Keep bed quiet so game / VODs stay intelligible (not a ducking compressor).
DEFAULT_VOLUME = 0.10
_MIN_VOL = 0.01
_MAX_VOL = 0.35


def music_enabled(cfg: dict[str, Any] | None) -> bool:
    """True unless music.enabled is explicitly false. Default True (skip if no file)."""
    if not cfg:
        return True
    music = cfg.get("music")
    if isinstance(music, dict) and "enabled" in music:
        return bool(music["enabled"])
    return True


def music_volume(cfg: dict[str, Any] | None) -> float:
    """Bed volume relative to dialogue; clamped low so it never drowns game audio."""
    raw = DEFAULT_VOLUME
    if cfg and isinstance(cfg.get("music"), dict):
        try:
            raw = float(cfg["music"].get("volume", DEFAULT_VOLUME))
        except (TypeError, ValueError):
            raw = DEFAULT_VOLUME
    return max(_MIN_VOL, min(_MAX_VOL, raw))


def resolve_music_path(cfg: dict[str, Any] | None) -> Path | None:
    """Return music file path if it exists; else None (skip mix)."""
    rel = DEFAULT_MUSIC_REL
    if cfg and isinstance(cfg.get("music"), dict):
        raw = (cfg["music"].get("path") or "").strip()
        if raw:
            rel = raw
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path if path.is_file() and path.stat().st_size > 0 else None


def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return
    err = (proc.stderr or proc.stdout or "").strip()
    tail = "\n".join(err.splitlines()[-25:]) if err else "(no ffmpeg output)"
    raise RuntimeError(f"ffmpeg music mix failed (exit {proc.returncode}).\n{tail}")


def mix_music_bed(
    video: Path,
    music: Path,
    dest: Path,
    *,
    volume: float = DEFAULT_VOLUME,
) -> Path:
    """Mix ``music`` under ``video`` audio at ``volume``; video stream copied re-encode.

    Music loops if shorter than the clip. Duration follows the video (``duration=first``).
    """
    ffmpeg = require_ffmpeg()
    video = Path(video)
    music = Path(music)
    dest = Path(dest)
    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")
    if not music.exists():
        raise FileNotFoundError(f"music not found: {music}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    vol = max(_MIN_VOL, min(_MAX_VOL, float(volume)))

    # Loop music input; scale bed; amix with dialogue (video = first → duration).
    # normalize=0 keeps dialogue level; bed stays at explicit volume.
    filter_complex = (
        f"[1:a]volume={vol:.4f},aformat=sample_fmts=fltp:channel_layouts=stereo[bed];"
        f"[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo[dlg];"
        f"[dlg][bed]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-stream_loop",
        "-1",
        "-i",
        str(music),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-shortest",
        *COMPAT_VIDEO,
        *COMPAT_AUDIO,
        *COMPAT_MOVFLAGS,
        str(dest),
    ]
    _run_ffmpeg(cmd)
    return dest


def maybe_mix_music(
    video: Path,
    dest: Path,
    cfg: dict[str, Any],
) -> Path:
    """If music enabled and file present, mix bed into ``dest``; else return ``video``.

    Fail-soft: on any error, prints and returns the original ``video`` path.
    """
    if not music_enabled(cfg):
        return Path(video)
    music = resolve_music_path(cfg)
    if music is None:
        return Path(video)
    video = Path(video)
    dest = Path(dest)
    if not video.exists():
        return video
    try:
        mix_music_bed(video, music, dest, volume=music_volume(cfg))
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
    except Exception as exc:  # noqa: BLE001
        print(f"Music bed skipped: {exc}")
    return video


def maybe_mix_social_pair(
    horizontal: Path,
    vertical: Path,
    out_dir: Path,
    stamp: str,
    cfg: dict[str, Any],
) -> tuple[Path, Path]:
    """Mix music under both H and V outputs when configured; fail-soft per file."""
    out_dir = Path(out_dir)
    h_out = out_dir / f"clip-horizontal-music-{stamp}.mp4"
    v_out = out_dir / f"clip-vertical-music-{stamp}.mp4"
    h2 = maybe_mix_music(horizontal, h_out, cfg)
    v2 = maybe_mix_music(vertical, v_out, cfg)
    return h2, v2
