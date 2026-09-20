#!/usr/bin/env python3
"""Smoke: synth clip + quiet sine bed → amix; assert output exists (needs ffmpeg)."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript.music import mix_music_bed, maybe_mix_music, music_volume
from subscript.clip import require_ffmpeg


def main() -> None:
    require_ffmpeg()
    out = Path("out/smoke_music")
    out.mkdir(parents=True, exist_ok=True)
    video = out / "src.mp4"
    bed = out / "bed.mp3"
    dest = out / "mixed.mp4"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=640x360:r=30",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100",
            "-t", "2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
            "-t", "3",
            "-c:a", "libmp3lame", "-q:a", "4",
            str(bed),
        ],
        check=True,
        capture_output=True,
    )
    mix_music_bed(video, bed, dest, volume=0.10)
    assert dest.exists() and dest.stat().st_size > 0

    # Fail-soft: missing music returns original
    cfg = {"music": {"enabled": True, "path": "assets/no-such-music.mp3", "volume": 0.10}}
    same = maybe_mix_music(video, out / "skip.mp4", cfg)
    assert same == video

    # Disabled returns original
    cfg2 = {"music": {"enabled": False, "path": str(bed), "volume": 0.10}}
    same2 = maybe_mix_music(video, out / "off.mp4", cfg2)
    assert same2 == video

    assert abs(music_volume({"music": {"volume": 0.99}}) - 0.35) < 1e-6
    print("PASS", dest)


if __name__ == "__main__":
    main()
