"""Shared fixtures: ffmpeg detection, synthetic videos, and an isolated FastAPI app."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from subscript.runtime_paths import find_ffmpeg

FFMPEG = find_ffmpeg()

needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg binary not found")


def _synth(dest: Path, seconds: float = 2.0, size: str = "640x360") -> Path:
    """Tiny H.264 + AAC test clip (colour bars + 440 Hz tone)."""
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", str(seconds),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


@pytest.fixture
def synth_video(tmp_path: Path) -> Path:
    if FFMPEG is None:
        pytest.skip("ffmpeg binary not found")
    return _synth(tmp_path / "synth.mp4")


@pytest.fixture
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A review app wired to a throwaway output dir; never touches the real config.yaml."""
    from fastapi.testclient import TestClient

    from subscript.live_app import create_app
    from subscript.queue import ReviewQueue

    out_dir = tmp_path / "out"
    cfg = {
        "buffer_seconds": 30,
        "brand": {
            "logo_path": "assets/logo.png",
            "opacity": 0.85,
            "position": "bottom_right",
            "margin_px": 24,
        },
        "captions": {"enabled": True, "engine": "demo"},
        "music": {"enabled": False},
        "output": {
            "dir": str(out_dir),
            # Small frames keep the ffmpeg-backed tests fast.
            "shorts_width": 270,
            "shorts_height": 480,
            "landscape_width": 320,
            "landscape_height": 180,
        },
        "review": {"host": "127.0.0.1", "port": 8787, "require_approval": True},
        "youtube": {"enabled": False},
        "platforms": {"tiktok": {"enabled": True, "mode": "manual"}},
    }
    monkeypatch.setenv("SUB_SCRIPT_NO_OPEN", "1")
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr("subscript.config.DEFAULT_CONFIG", cfg_path)
    monkeypatch.setattr("subscript.config_polish.DEFAULT_CONFIG", cfg_path)
    monkeypatch.setattr("subscript.branding_routes.ASSETS_DIR", tmp_path / "assets")

    app = create_app(cfg)
    client = TestClient(app)
    return SimpleNamespace(
        client=client,
        cfg=cfg,
        cfg_path=cfg_path,
        out_dir=out_dir,
        queue=ReviewQueue(out_dir / "review-queue.json"),
        tmp=tmp_path,
    )
