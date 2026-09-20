#!/usr/bin/env python3
"""Smoke: demo SRT burn + engine resolve fail-soft (needs ffmpeg; whisper optional)."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript.captions import (
    burn_captions,
    captions_engine,
    resolve_srt_for_video,
    whisper_available,
    write_demo_srt,
)
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
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(src),
        ],
        check=True,
        capture_output=True,
    )
    write_demo_srt(srt, 3.0)
    assert srt.exists() and srt.stat().st_size > 0
    burn_captions(src, srt, dest)
    assert dest.exists() and dest.stat().st_size > 0

    # demo engine always writes demo
    srt2 = out / "engine.srt"
    path, label = resolve_srt_for_video(src, srt2, 3.0, {"captions": {"engine": "demo"}})
    assert path.exists() and label == "demo"
    assert "Clip | SUB" in path.read_text(encoding="utf-8")

    # auto without whisper → demo
    if not whisper_available():
        srt3 = out / "auto.srt"
        _, label3 = resolve_srt_for_video(src, srt3, 3.0, {"captions": {"engine": "auto"}})
        assert label3 == "demo"
        # whisper engine without install still demos
        srt4 = out / "force.srt"
        _, label4 = resolve_srt_for_video(src, srt4, 3.0, {"captions": {"engine": "whisper"}})
        assert label4 == "demo"

    assert captions_engine({"captions": {"engine": "Whisper"}}) == "whisper"
    print("PASS", dest, "whisper_available=", whisper_available())


if __name__ == "__main__":
    main()
