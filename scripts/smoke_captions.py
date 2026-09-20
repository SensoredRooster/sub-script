#!/usr/bin/env python3
"""Smoke test: 3s color+sine mp4 → demo SRT → burn captions (needs ffmpeg)."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript.captions import burn_captions, write_demo_srt
from subscript.clip import require_ffmpeg


def main() -> None:
    require_ffmpeg()
    out = Path("out/smoke_captions")
    out.mkdir(parents=True, exist_ok=True)
    src = out / "src.mp4"
    srt = out / "demo.srt"
    dest = out / "captioned.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=720x1280:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    write_demo_srt(srt, 3.0)
    assert srt.exists() and srt.stat().st_size > 0
    burn_captions(src, srt, dest)
    assert dest.exists() and dest.stat().st_size > 0
    print("PASS", dest)


if __name__ == "__main__":
    main()
