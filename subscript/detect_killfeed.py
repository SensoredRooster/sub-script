"""Experimental v0: Warzone/CoD kill-feed OCR (optional engines).

Samples VOD frames with ffmpeg, crops a configurable ROI (fractions of the
stream frame — locked to ``stream.resolution`` when set), and looks for the
user's **exact** in-game player name in OCR text so other players' kills do
not fire.

OCR is optional: try ``easyocr`` then ``pytesseract``. If neither is installed,
callers get an empty kill list plus a clear note — the app still runs on
loudness-only highlights.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from subscript.clip import require_ffmpeg

# Default Warzone-ish kill feed: top-right portion of a 16:9 HUD.
_DEFAULT_ROI = {"x": 0.62, "y": 0.02, "w": 0.36, "h": 0.28}


def detect_enabled(cfg: dict[str, Any] | None) -> bool:
    """True only when ``detect.enabled`` is explicitly true."""
    if not cfg:
        return False
    det = cfg.get("detect")
    if isinstance(det, dict):
        return bool(det.get("enabled"))
    return False


def resolve_player_name(cfg: dict[str, Any] | None) -> str:
    """Exact in-game name: ``detect.player_name`` or ``stream.player_name``."""
    if not cfg:
        return ""
    det = cfg.get("detect") if isinstance(cfg.get("detect"), dict) else {}
    name = str(det.get("player_name") or "").strip()
    if name:
        return name
    stream = cfg.get("stream") if isinstance(cfg.get("stream"), dict) else {}
    return str(stream.get("player_name") or "").strip()


def resolve_roi(cfg: dict[str, Any] | None) -> dict[str, float]:
    """Return ROI as fractions of frame width/height (0..1), clamped."""
    roi = dict(_DEFAULT_ROI)
    if cfg and isinstance(cfg.get("detect"), dict):
        raw = cfg["detect"].get("roi")
        if isinstance(raw, dict):
            for key in ("x", "y", "w", "h"):
                if key in raw:
                    try:
                        roi[key] = float(raw[key])
                    except (TypeError, ValueError):
                        pass
    # Clamp + keep box inside the frame.
    x = min(1.0, max(0.0, float(roi["x"])))
    y = min(1.0, max(0.0, float(roi["y"])))
    w = min(1.0 - x, max(0.01, float(roi["w"])))
    h = min(1.0 - y, max(0.01, float(roi["h"])))
    return {"x": x, "y": y, "w": w, "h": h}


def resolve_stream_size(cfg: dict[str, Any] | None) -> tuple[int, int] | None:
    """Parse ``stream.resolution`` like ``1920x1080`` → (w, h), or None."""
    if not cfg:
        return None
    stream = cfg.get("stream") if isinstance(cfg.get("stream"), dict) else {}
    raw = str(stream.get("resolution") or "").strip().lower()
    m = re.match(r"^(\d+)\s*[x×]\s*(\d+)$", raw)
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    if w < 16 or h < 16:
        return None
    return w, h


def sample_fps(cfg: dict[str, Any] | None) -> float:
    """Frames per second to sample (default 1.0)."""
    if cfg and isinstance(cfg.get("detect"), dict):
        try:
            fps = float(cfg["detect"].get("sample_fps") or 1.0)
            return max(0.1, min(10.0, fps))
        except (TypeError, ValueError):
            pass
    return 1.0


def ocr_engines_available() -> dict[str, bool]:
    """Which optional OCR backends import cleanly (never hard-required)."""
    easy = False
    tess = False
    try:
        import easyocr  # noqa: F401

        easy = True
    except Exception:
        easy = False
    try:
        import pytesseract  # noqa: F401

        tess = True
    except Exception:
        tess = False
    return {"easyocr": easy, "pytesseract": tess}


def ocr_available() -> bool:
    return any(ocr_engines_available().values())


def roi_pixel_box(
    frame_w: int,
    frame_h: int,
    roi: dict[str, float],
) -> tuple[int, int, int, int]:
    """Convert ROI fractions → inclusive pixel crop ``(x, y, w, h)``.

    Locked to the given frame size (stream resolution or probed frame).
    """
    x0 = int(round(frame_w * float(roi["x"])))
    y0 = int(round(frame_h * float(roi["y"])))
    rw = max(1, int(round(frame_w * float(roi["w"]))))
    rh = max(1, int(round(frame_h * float(roi["h"]))))
    x0 = min(max(0, x0), max(0, frame_w - 1))
    y0 = min(max(0, y0), max(0, frame_h - 1))
    rw = min(rw, frame_w - x0)
    rh = min(rh, frame_h - y0)
    return x0, y0, max(1, rw), max(1, rh)


def probe_video_size(source: Path) -> tuple[int, int]:
    """Best-effort video width/height via ffprobe."""
    ffmpeg = require_ffmpeg()
    ffprobe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        text = (proc.stdout or "").strip().splitlines()
        if text:
            m = re.match(r"^(\d+)x(\d+)", text[0].strip())
            if m:
                return int(m.group(1)), int(m.group(2))
    raise RuntimeError("ffprobe could not read video size")
