"""Apply logo / reusable intro/outro branding with ffmpeg."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from subscript.clip import (
    COMPAT_AUDIO,
    COMPAT_MOVFLAGS,
    COMPAT_VIDEO,
    require_ffmpeg,
    run_ffmpeg,
)
from subscript.runtime_paths import app_dir, find_ffprobe

_POSITIONS = {
    "top_left": "10:10",
    "top_right": "W-w-10:10",
    "bottom_left": "10:H-h-10",
    "bottom_right": "W-w-10:H-h-10",
}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _run_ffmpeg(cmd: list[str]) -> None:
    run_ffmpeg(cmd, what="ffmpeg brand overlay")


def apply_brand(source: Path, dest: Path, brand: dict[str, Any]) -> Path:
    """Overlay logo if present; always re-encode for player compatibility."""
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    logo_raw = str(brand.get("logo_path") or "").strip()
    logo = Path(logo_raw) if logo_raw else None
    if logo is not None and not logo.is_absolute():
        # Relative to the app folder: repo root from source, or the folder
        # beside SubScript.exe when frozen (``__file__`` lives inside _internal there).
        candidate = app_dir() / logo
        if candidate.is_file():
            logo = candidate
    margin = int(brand.get("margin_px") or 24)
    pos_key = brand.get("position") or "bottom_right"
    overlay = {
        "top_left": f"{margin}:{margin}",
        "top_right": f"W-w-{margin}:{margin}",
        "bottom_left": f"{margin}:H-h-{margin}",
        "bottom_right": f"W-w-{margin}:H-h-{margin}",
    }.get(pos_key, _POSITIONS["bottom_right"])

    if logo is not None and logo.is_file() and logo.stat().st_size > 0:
        opacity = float(brand.get("opacity") or 0.85)
        opacity = max(0.05, min(1.0, opacity))
        # Scale badge down so it never exceeds ~180px / source frame
        filter_complex = (
            f"[1:v]scale=180:-1:flags=lanczos,format=rgba,"
            f"colorchannelmixer=aa={opacity}[logo];"
            f"[0:v][logo]overlay={overlay}:format=auto[outv]"
        )
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-i",
            str(logo),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            *COMPAT_VIDEO,
            *COMPAT_AUDIO,
            *COMPAT_MOVFLAGS,
            str(dest),
        ]
        try:
            _run_ffmpeg(cmd)
            return dest
        except RuntimeError:
            # Retry without optional-audio syntax (some Windows ffmpeg builds choke on 0:a?)
            cmd_no_opt = [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-i",
                str(logo),
                "-filter_complex",
                filter_complex,
                "-map",
                "[outv]",
                "-map",
                "0:a",
                *COMPAT_VIDEO,
                *COMPAT_AUDIO,
                *COMPAT_MOVFLAGS,
                str(dest),
            ]
            try:
                _run_ffmpeg(cmd_no_opt)
                return dest
            except RuntimeError:
                # Last resort: video-only overlay (still branded)
                cmd_silent = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(source),
                    "-i",
                    str(logo),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[outv]",
                    "-an",
                    *COMPAT_VIDEO,
                    *COMPAT_MOVFLAGS,
                    str(dest),
                ]
                try:
                    _run_ffmpeg(cmd_silent)
                    return dest
                except RuntimeError:
                    # Give up on logo — still deliver a playable clip
                    pass

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        *COMPAT_VIDEO,
        *COMPAT_AUDIO,
        *COMPAT_MOVFLAGS,
        str(dest),
    ]
    _run_ffmpeg(cmd)
    return dest


def _asset_paths(brand: dict[str, Any], key: str) -> list[Path]:
    """Resolve configured intro/outro paths and ignore missing files safely."""
    raw = brand.get(key) or []
    if isinstance(raw, str):
        raw = [raw]
    paths: list[Path] = []
    for value in raw if isinstance(raw, list) else []:
        path = Path(str(value))
        if not path.is_absolute():
            path = app_dir() / path
        if path.is_file() and path.suffix.lower() in _VIDEO_SUFFIXES and path.stat().st_size:
            paths.append(path)
    return paths


def choose_sequence_assets(brand: dict[str, Any], stamp: str) -> tuple[Path | None, Path | None]:
    """Pick one configured intro and outro for this render.

    A deterministic pick keeps a repeated render predictable while rotating through
    multiple uploaded variants across clips. Missing files are simply skipped.
    """
    chosen: list[Path | None] = []
    for key in ("intro_paths", "outro_paths"):
        paths = _asset_paths(brand, key)
        if not paths:
            chosen.append(None)
            continue
        try:
            index = int("".join(ch for ch in stamp if ch.isdigit())[-6:]) % len(paths)
        except ValueError:
            index = 0
        chosen.append(paths[index])
    return chosen[0], chosen[1]


def compose_brand_sequence(
    parts: list[Path], dest: Path, *, width: int = 1920, height: int = 1080
) -> Path:
    """Join intro + main + outro into one consistent H.264/AAC master.

    The filter graph normalizes dimensions, frame rate, timestamps and audio so
    creators can upload ready-made intros/outros from different editors.
    """
    if len(parts) < 2:
        raise ValueError("A branded sequence needs at least two video parts.")
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    input_index = 0
    for index, path in enumerate(parts):
        inputs.extend(["-i", str(path)])
        video_index = input_index
        input_index += 1
        audio_index = video_index
        has_audio, duration = _probe_audio(path)
        if not has_audio:
            # A silent bumper is valid; give concat a matching silent track.
            inputs.extend(["-f", "lavfi", "-t", str(duration or 1.0), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
            audio_index = input_index
            input_index += 1
        filters.append(
            f"[{video_index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{index}]"
        )
        audio_filter = f"[{audio_index}:a]aresample=48000,apad"
        if duration:
            audio_filter += f",atrim=duration={duration:g}"
        filters.append(
            audio_filter + f",asetpts=PTS-STARTPTS[a{index}]"
        )
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(parts)))
    filters.append(f"{concat_inputs}concat=n={len(parts)}:v=1:a=1[outv][outa]")
    cmd = [
        ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-map", "[outa]", *COMPAT_VIDEO,
        *COMPAT_AUDIO, *COMPAT_MOVFLAGS, str(dest),
    ]
    _run_ffmpeg(cmd)
    return dest


def _probe_audio(path: Path) -> tuple[bool, float | None]:
    """Best-effort stream probe used to support silent intro/outro files."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return True, None
    try:
        audio = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        duration = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        value = float(duration.stdout.strip()) if duration.stdout.strip() else None
        return bool(audio.stdout.strip()), value if value and value > 0 else None
    except (OSError, ValueError):
        return True, None
