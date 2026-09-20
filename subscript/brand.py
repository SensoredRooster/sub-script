"""Apply logo / text overlay with ffmpeg (always H.264 + AAC out)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.clip import (
    COMPAT_AUDIO,
    COMPAT_MOVFLAGS,
    COMPAT_VIDEO,
    require_ffmpeg,
    run_ffmpeg,
)
from subscript.runtime_paths import app_dir

_POSITIONS = {
    "top_left": "10:10",
    "top_right": "W-w-10:10",
    "bottom_left": "10:H-h-10",
    "bottom_right": "W-w-10:H-h-10",
}


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
