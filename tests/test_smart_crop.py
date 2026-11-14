"""Smart vertical reframe: motion-anchored crop placement."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from subscript import smart_crop
from subscript.layout import smart_vertical_filter


def _synth_video(dest: Path, *, moving: str = "left", seconds: int = 6) -> Path:
    """Small synthetic clip: bright box bouncing on one side over dark static."""
    from subscript.clip import require_ffmpeg

    ffmpeg = require_ffmpeg()
    if moving == "left":
        x_expr = "60+40*sin(2*PI*t)"
    elif moving == "right":
        x_expr = "700+40*sin(2*PI*t)"
    else:
        x_expr = None
    if x_expr:
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", f"color=c=0x202020:s=960x540:d={seconds}:r=10",
            "-f", "lavfi", "-i", f"color=c=white:s=120x120:d={seconds}:r=10",
            "-filter_complex", f"[0:v][1:v]overlay=x='{x_expr}':y=200:eval=frame",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(dest),
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", f"color=c=0x808080:s=960x540:d={seconds}:r=10",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(dest),
        ]
    subprocess.run(cmd, capture_output=True, check=True)
    return dest


pytestmark = pytest.mark.skipif(
    __import__("subscript.runtime_paths", fromlist=["find_ffmpeg"]).find_ffmpeg() is None,
    reason="ffmpeg binary not found",
)


def test_anchor_follows_left_motion(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "left.mp4", moving="left")
    frac = smart_crop.motion_anchor_fraction(src)
    assert frac is not None
    assert frac < 0.35, f"expected left-anchored, got {frac}"


def test_anchor_follows_right_motion(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "right.mp4", moving="right")
    frac = smart_crop.motion_anchor_fraction(src)
    assert frac is not None
    assert frac > 0.65, f"expected right-anchored, got {frac}"


def test_uniform_video_returns_none(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "flat.mp4", moving="none")
    assert smart_crop.motion_anchor_fraction(src) is None


def test_smart_crop_x_offsets_left(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "left.mp4", moving="left")
    x = smart_crop.smart_crop_x(src, 960, 540, 1080, 1920)
    assert x is not None
    crop_w = 540 * 1080 // 1920  # 303 -> 302 even
    center = (960 - crop_w) // 2
    assert x < center


def test_smart_crop_x_clamps_to_frame(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "right.mp4", moving="right")
    x = smart_crop.smart_crop_x(src, 960, 540, 1080, 1920)
    assert x is not None
    crop_w = 540 * 1080 // 1920
    crop_w -= crop_w % 2
    assert 0 <= x <= 960 - crop_w


def test_smart_vertical_filter_falls_back_without_signal(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "flat.mp4", moving="none")
    vf = smart_vertical_filter(src, 1080, 1920)
    assert vf == "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"


def test_smart_vertical_filter_disabled() -> None:
    vf = smart_vertical_filter(Path("nonexistent.mp4"), 1080, 1920, smart=False)
    assert vf == "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"


def test_smart_vertical_filter_smart_path(tmp_path: Path) -> None:
    src = _synth_video(tmp_path / "left.mp4", moving="left")
    vf = smart_vertical_filter(src, 1080, 1920, smart=True)
    assert vf.startswith("crop=")
    assert "scale=1080:1920" in vf and "setsar=1" in vf
