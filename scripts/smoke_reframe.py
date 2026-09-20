#!/usr/bin/env python3
"""Smoke test: generate a short clip then H+V reframes (needs ffmpeg)."""
from pathlib import Path
import subprocess, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript.reframe import make_social_pair
from subscript.clip import require_ffmpeg

def main() -> None:
    require_ffmpeg()
    out = Path("out/smoke")
    out.mkdir(parents=True, exist_ok=True)
    src = out / "src.mp4"
    # 2s color bars
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)
    ], check=True, capture_output=True)
    h, v = make_social_pair(src, out, "smoke")
    assert h.exists() and v.exists() and h.stat().st_size > 0 and v.stat().st_size > 0
    print("PASS", h, v)

if __name__ == "__main__":
    main()
