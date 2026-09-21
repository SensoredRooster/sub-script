"""Make horizontal (16:9) and vertical (9:16) social-ready versions."""

from __future__ import annotations

from pathlib import Path

from subscript.clip import (
    COMPAT_AUDIO,
    COMPAT_MOVFLAGS,
    COMPAT_VIDEO,
    require_ffmpeg,
    run_ffmpeg,
)
from subscript.layout import make_vertical_with_layout


def _run(cmd: list[str]) -> None:
    run_ffmpeg(cmd, what="ffmpeg reframe")


def make_horizontal(source: Path, dest: Path, width: int = 1920, height: int = 1080) -> Path:
    """Center-crop/pad to 16:9."""
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    cmd = [
        ffmpeg, "-y", "-i", str(source),
        "-vf", vf,
        *COMPAT_VIDEO, *COMPAT_AUDIO, *COMPAT_MOVFLAGS,
        str(dest),
    ]
    _run(cmd)
    return dest


def make_vertical(
    source: Path,
    dest: Path,
    width: int = 1080,
    height: int = 1920,
    layout: dict | None = None,
) -> Path:
    """Render a true 9:16 output, optionally using a normalized composer template."""
    if layout:
        return make_vertical_with_layout(source, dest, width=width, height=height, layout=layout)
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    cmd = [ffmpeg, "-y", "-i", str(source), "-vf", vf, *COMPAT_VIDEO, *COMPAT_AUDIO, *COMPAT_MOVFLAGS, str(dest)]
    _run(cmd)
    return dest


def make_social_pair(
    source: Path,
    out_dir: Path,
    stamp: str,
    *,
    shorts_w: int = 1080,
    shorts_h: int = 1920,
    landscape_w: int = 1920,
    landscape_h: int = 1080,
    vertical_layout: dict | None = None,
) -> tuple[Path, Path]:
    horizontal = out_dir / f"clip-horizontal-{stamp}.mp4"
    vertical = out_dir / f"clip-vertical-{stamp}.mp4"
    make_horizontal(source, horizontal, width=landscape_w, height=landscape_h)
    make_vertical(source, vertical, width=shorts_w, height=shorts_h, layout=vertical_layout)
    return horizontal, vertical
