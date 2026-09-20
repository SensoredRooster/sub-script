#!/usr/bin/env python3
"""Smoke: ROI crop works without OCR; exact name match; detect fail-soft."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript.clip import require_ffmpeg
from subscript.detect_killfeed import (
    detect_kills,
    ocr_available,
    player_name_in_text,
    resolve_roi,
    resolve_stream_size,
    roi_pixel_box,
    sample_roi_frames,
)
from subscript.highlights import suggest_highlights_or_fallback


def _make_short_vod(out: Path) -> Path:
    require_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    # 1920x1080 black 3s — matches stream.resolution lock for ROI fractions.
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=1920x1080:r=10:d=3",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=220:sample_rate=44100:duration=3",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"ffmpeg synth failed:\n{err}")
    return out


def main() -> None:
    require_ffmpeg()
    out_dir = Path("out/smoke_killfeed")
    out_dir.mkdir(parents=True, exist_ok=True)
    src = _make_short_vod(out_dir / "hud.mp4")

    # Exact name match (constraint 2)
    assert player_name_in_text("SensoredRooster killed Foo", "SensoredRooster")
    assert not player_name_in_text("Enemy killed Foo", "SensoredRooster")
    assert not player_name_in_text("SensoredRoosterX killed Foo", "SensoredRooster")

    cfg = {
        "stream": {"resolution": "1920x1080", "player_name": "SensoredRooster"},
        "detect": {
            "enabled": True,
            "player_name": "SensoredRooster",
            "sample_fps": 1.0,
            "roi": {"x": 0.62, "y": 0.02, "w": 0.36, "h": 0.28},
        },
    }
    # ROI locked to stream resolution (constraint 1)
    size = resolve_stream_size(cfg)
    assert size == (1920, 1080)
    roi = resolve_roi(cfg)
    box = roi_pixel_box(size[0], size[1], roi)
    assert box[0] + box[2] <= 1920 and box[1] + box[3] <= 1080

    roi_dir = out_dir / "roi"
    if roi_dir.exists():
        for p in roi_dir.glob("*.png"):
            p.unlink()
    frames = sample_roi_frames(
        src, roi_dir, roi=roi, fps=1.0, frame_size=size, max_frames=5
    )
    assert frames, "expected ROI PNGs without OCR"
    for _t, path in frames:
        assert path.is_file() and path.stat().st_size > 0, path

    # OCR optional (constraint 3): detect returns empty + clear note
    result = detect_kills(src, player_name="SensoredRooster", cfg=cfg, work_dir=out_dir / "detect_work")
    assert isinstance(result["kills"], list)
    if not ocr_available():
        assert result["kills"] == []
        assert "OCR engine not installed" in (result.get("note") or "")
        print("OCR absent — stub note OK")
    else:
        print("OCR present — engines may return hits on blank HUD (ok)")

    # Highlights fail-soft merge path (loudness still works)
    payload = suggest_highlights_or_fallback(
        src, buffer_seconds=2.0, top_n=2, cfg=cfg
    )
    assert payload["suggestions"], "loudness/fallback suggestions required"
    assert "detect_note" in payload
    if not ocr_available():
        assert "OCR" in payload["detect_note"] or "loudness" in payload["detect_note"].lower() or "kill" in payload["detect_note"].lower()

    print("PASS", src)
    print("roi_frames", len(frames), "box", box)
    print("detect_note", (payload.get("detect_note") or "")[:120])
    print("ocr_available", ocr_available())


if __name__ == "__main__":
    main()
