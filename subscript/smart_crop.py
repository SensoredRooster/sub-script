"""Motion-anchored reframing: place the vertical crop window where the action is.

A dead-center 9:16 crop is wrong whenever the action happens off-center (HUD
elements get sliced, the subject walks out of frame). This module samples the
clip at low resolution, builds a per-column motion-energy profile from frame
differences, and returns the source-space x offset that centers the crop window
on the action. Everything is fail-soft: any problem means "use center", which
is exactly the old behavior.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from subscript.clip import require_ffmpeg

# Tiny grayscale analysis grid: big enough to locate action, small enough that
# a 30 s clip analyzes in a couple of seconds with pure-Python differencing.
_ANALYZE_W = 160
_ANALYZE_H = 90
_MAX_FRAMES = 45


def _column_motion(source: Path) -> list[float] | None:
    """Per-column summed squared frame-difference energy, or None on failure."""
    ffmpeg = require_ffmpeg()
    cmd = [
        ffmpeg, "-v", "error",
        "-i", str(source),
        "-vf", f"fps=1.5,scale={_ANALYZE_W}:{_ANALYZE_H},format=gray",
        "-frames:v", str(_MAX_FRAMES),
        "-f", "rawvideo", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = proc.stdout
    frame_bytes = _ANALYZE_W * _ANALYZE_H
    n = len(raw) // frame_bytes
    if proc.returncode != 0 or n < 2:
        return None

    energy = [0.0] * _ANALYZE_W
    prev = raw[:frame_bytes]
    for i in range(1, n):
        cur = raw[i * frame_bytes : (i + 1) * frame_bytes]
        # Skip every other row for speed; columns keep full resolution.
        for y in range(0, _ANALYZE_H, 2):
            base = y * _ANALYZE_W
            for x in range(_ANALYZE_W):
                d = cur[base + x] - prev[base + x]
                energy[x] += d * d
        prev = cur
    return energy


def _smooth(values: list[float], radius: int = 6) -> list[float]:
    out = []
    n = len(values)
    for i in range(n):
        lo, hi = max(0, i - radius), min(n, i + radius + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def motion_anchor_fraction(source: Path) -> float | None:
    """Return the horizontal center of action as a 0..1 frame fraction.

    Uses the weighted centroid of above-median motion columns so steady HUD
    flicker (kill feeds, minimaps) can't drag the window on its own. Returns
    None when there is no usable signal (static clip, decode failure).
    """
    energy = _column_motion(Path(source))
    if not energy:
        return None
    smoothed = _smooth(energy)
    total = sum(smoothed)
    if total <= 0:
        return None
    peak = max(smoothed)
    if peak <= 0:
        return None
    # If motion is perfectly uniform (e.g. full-screen video noise), the
    # centroid is just the middle — say so by returning None → center crop.
    if peak / (total / len(smoothed)) < 1.15:
        return None
    floor = sorted(smoothed)[len(smoothed) // 2]  # median
    num = 0.0
    den = 0.0
    for x, e in enumerate(smoothed):
        if e > floor:
            w = e - floor
            num += (x + 0.5) / len(smoothed) * w
            den += w
    if den <= 0:
        return None
    return num / den


def smart_crop_x(
    source: Path,
    src_w: int,
    src_h: int,
    target_w: int,
    target_h: int,
) -> int | None:
    """Source-space x offset for a target-aspect crop anchored on motion.

    Returns None when smart placement has no signal — callers fall back to
    ffmpeg's default centering, which is the pre-existing behavior.
    """
    if src_w < 2 or src_h < 2 or target_w < 2 or target_h < 2:
        return None
    # Crop window in source pixels matching the target aspect ratio.
    crop_w = int(round(src_h * target_w / target_h))
    crop_w -= crop_w % 2  # keep even for yuv420p
    if crop_w >= src_w or crop_w < 2:
        return None
    anchor = motion_anchor_fraction(source)
    if anchor is None:
        return None
    x = int(round(anchor * src_w - crop_w / 2))
    return max(0, min(src_w - crop_w, x))
