"""Apply logo / text overlay with ffmpeg (always H.264 + AAC out)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from subscript.clip import COMPAT_AUDIO, COMPAT_MOVFLAGS, COMPAT_VIDEO, require_ffmpeg

_POSITIONS = {
    "top_left": "10:10",
    "top_right": "W-w-10:10",
    "bottom_left": "10:H-h-10",
    "bottom_right": "W-w-10:H-h-10",
}


def apply_brand(source: Path, dest: Path, brand: dict[str, Any]) -> Path:
    """Overlay logo if present; always re-encode for player compatibility."""
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    logo = Path(brand.get("logo_path") or "")
    margin = int(brand.get("margin_px") or 24)
    pos_key = brand.get("position") or "bottom_right"
    overlay = {
        "top_left": f"{margin}:{margin}",
        "top_right": f"W-w-{margin}:{margin}",
        "bottom_left": f"{margin}:H-h-{margin}",
        "bottom_right": f"W-w-{margin}:H-h-{margin}",
    }.get(pos_key, _POSITIONS["bottom_right"])

    if logo.exists():
        opacity = float(brand.get("opacity") or 0.85)
        filter_complex = (
            f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[logo];"
            f"[0:v][logo]overlay={overlay}[outv]"
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
    else:
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

    subprocess.run(cmd, check=True, capture_output=True)
    return dest
