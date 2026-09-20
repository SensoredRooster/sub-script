#!/usr/bin/env python3
"""Smoke: synthetic quiet/loud/quiet audio → auto-highlight peaks near the loud part."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript.clip import require_ffmpeg
from subscript.highlights import suggest_highlights, suggest_highlights_or_fallback


def _make_synthetic(out: Path) -> Path:
    """60s video: quiet (0-20) → loud (20-40) → quiet (40-60)."""
    require_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x240:r=10:d=60",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:duration=60",
        "-filter_complex",
        (
            "[1:a]volume=0.05[a0];"
            "[1:a]volume=1.0[a1];"
            "[1:a]volume=0.05[a2];"
            "[a0]atrim=0:20,asetpts=PTS-STARTPTS[q1];"
            "[a1]atrim=20:40,asetpts=PTS-STARTPTS[loud];"
            "[a2]atrim=40:60,asetpts=PTS-STARTPTS[q2];"
            "[q1][loud][q2]concat=n=3:v=0:a=1[a]"
        ),
        "-map",
        "0:v",
        "-map",
        "[a]",
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
        cmd2 = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:r=10:d=60",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0.05*sin(2*PI*440*t):s=44100:d=20",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0.9*sin(2*PI*440*t):s=44100:d=20",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0.05*sin(2*PI*440*t):s=44100:d=20",
            "-filter_complex",
            "[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ]
        proc2 = subprocess.run(cmd2, capture_output=True)
        if proc2.returncode != 0:
            err = (proc2.stderr or b"").decode("utf-8", errors="replace")[-600:]
            raise RuntimeError(f"ffmpeg synth failed:\n{err}")
    return out


def main() -> None:
    require_ffmpeg()
    out_dir = Path("out/smoke_highlights")
    out_dir.mkdir(parents=True, exist_ok=True)
    src = _make_synthetic(out_dir / "loud_quiet.mp4")
    assert src.exists() and src.stat().st_size > 0

    suggestions = suggest_highlights(src, buffer_seconds=10.0, top_n=3)
    assert suggestions, "expected at least one suggestion"
    assert all("start" in s and "duration" in s and "score" in s for s in suggestions)

    best = max(suggestions, key=lambda s: float(s["score"]))
    best_start = float(best["start"])
    best_mid = best_start + float(best["duration"]) / 2.0
    assert 15.0 <= best_mid <= 45.0, (
        f"expected loud peak mid around 20-40s, got mid={best_mid} suggestions={suggestions}"
    )

    payload = suggest_highlights_or_fallback(src, buffer_seconds=10.0, top_n=3)
    assert payload["fallback"] is False
    assert payload["suggestions"]

    missing = suggest_highlights_or_fallback(
        out_dir / "does-not-exist.mp4", buffer_seconds=30.0, top_n=3
    )
    assert missing["fallback"] is True
    assert missing["suggestions"]
    assert missing["suggestions"][0]["start"] is None
    assert "fail" in missing["message"].lower() or "fall" in missing["message"].lower()

    print("PASS", src)
    print("suggestions", suggestions)
    print("fallback_ok", missing["message"][:80])


if __name__ == "__main__":
    main()
