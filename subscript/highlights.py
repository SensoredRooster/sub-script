"""Suggest highlight windows from VOD audio loudness (no ML).

Uses ffmpeg to sample mono PCM, scores sliding windows of ``buffer_seconds``
by RMS energy, and returns the top non-overlapping peaks. Fail-soft callers
should catch errors and fall back to last-N seconds.
"""

from __future__ import annotations

import math
import struct
import subprocess
from pathlib import Path
from typing import Any

from subscript.clip import require_ffmpeg

# Downsample for fast analysis (loudness shape is enough at 8 kHz mono).
_SAMPLE_RATE = 8000
_SAMPLE_FMT = "f32le"
_BYTES_PER_SAMPLE = 4


def suggest_highlights(
    source: Path,
    *,
    buffer_seconds: float = 30.0,
    top_n: int = 5,
    hop_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Return top-N peak segments as ``{start, duration, score}``.

    ``score`` is normalized 0..1 relative to the loudest window (1.0 = loudest).
    Windows do not overlap (greedy by score, then by start).
    """
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")

    duration = float(buffer_seconds)
    if duration <= 0:
        raise ValueError("buffer_seconds must be > 0")

    top_n = max(1, int(top_n))
    hop = float(hop_seconds) if hop_seconds is not None else max(1.0, duration / 3.0)

    samples = _decode_mono_pcm(source)
    if not samples:
        raise RuntimeError("No audio samples decoded (missing or silent track?)")

    total_sec = len(samples) / float(_SAMPLE_RATE)
    if total_sec <= 0:
        raise RuntimeError("Audio duration is zero")

    # Short VOD: single window covering what we have.
    win_sec = min(duration, total_sec)
    win_samples = max(1, int(round(win_sec * _SAMPLE_RATE)))
    hop_samples = max(1, int(round(hop * _SAMPLE_RATE)))

    windows: list[tuple[float, float, float]] = []  # (score_raw, start, duration)
    if len(samples) <= win_samples:
        rms = _rms(samples)
        windows.append((rms, 0.0, float(len(samples)) / _SAMPLE_RATE))
    else:
        i = 0
        while i + win_samples <= len(samples):
            chunk = samples[i : i + win_samples]
            rms = _rms(chunk)
            start = i / float(_SAMPLE_RATE)
            windows.append((rms, start, win_sec))
            i += hop_samples
        # Ensure the final window that ends at EOF is considered.
        last_start_i = len(samples) - win_samples
        if last_start_i > 0 and (not windows or windows[-1][1] < last_start_i / _SAMPLE_RATE - 0.01):
            chunk = samples[last_start_i:]
            windows.append((_rms(chunk), last_start_i / float(_SAMPLE_RATE), win_sec))

    if not windows:
        raise RuntimeError("No analysis windows produced")

    # Prefer loud over quiet; break ties earlier in the VOD.
    windows.sort(key=lambda w: (-w[0], w[1]))
    peak = windows[0][0]
    if peak <= 0 or math.isclose(peak, 0.0):
        # Flat silence — still return evenly spaced suggestions so UI has chips.
        span = max(0.0, total_sec - win_sec)
        step = span / max(1, top_n - 1) if top_n > 1 and span > 0 else 0.0
        out = []
        for n in range(top_n):
            start = min(span, n * step) if step else 0.0
            out.append(
                {
                    "start": round(start, 3),
                    "duration": round(win_sec, 3),
                    "score": 0.0,
                }
            )
        return out

    picked: list[dict[str, Any]] = []
    for rms, start, dur in windows:
        if len(picked) >= top_n:
            break
        end = start + dur
        overlap = False
        for p in picked:
            p0 = float(p["start"])
            p1 = p0 + float(p["duration"])
            if start < p1 and end > p0:
                overlap = True
                break
        if overlap:
            continue
        picked.append(
            {
                "start": round(start, 3),
                "duration": round(dur, 3),
                "score": round(min(1.0, max(0.0, rms / peak)), 4),
            }
        )

    picked.sort(key=lambda p: float(p["start"]))
    return picked


def suggest_highlights_or_fallback(
    source: Path,
    *,
    buffer_seconds: float = 30.0,
    top_n: int = 5,
) -> dict[str, Any]:
    """Analyze with fail-soft fallback to last ``buffer_seconds``.

    Returns a payload suitable for ``POST /highlights`` JSON::

        {
          "suggestions": [...],
          "fallback": bool,
          "message": str,
          "buffer_seconds": float,
        }
    """
    buf = float(buffer_seconds)
    try:
        suggestions = suggest_highlights(
            source, buffer_seconds=buf, top_n=top_n
        )
        return {
            "suggestions": suggestions,
            "fallback": False,
            "message": "",
            "buffer_seconds": buf,
        }
    except Exception as exc:  # noqa: BLE001 — intentional fail-soft
        return {
            "suggestions": [
                {
                    "start": None,
                    "duration": round(buf, 3),
                    "score": 0.0,
                }
            ],
            "fallback": True,
            "message": (
                f"Auto highlights failed ({exc}); "
                f"falling back to last {int(buf) if buf == int(buf) else buf} seconds."
            ),
            "buffer_seconds": buf,
        }


def _decode_mono_pcm(source: Path) -> list[float]:
    """Decode audio to mono float32 PCM via ffmpeg stdout."""
    ffmpeg = require_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(_SAMPLE_RATE),
        "-f",
        _SAMPLE_FMT,
        "-acodec",
        "pcm_f32le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[-400:]
        raise RuntimeError(f"ffmpeg audio decode failed: {err.strip() or 'no output'}")

    raw = proc.stdout
    n = len(raw) // _BYTES_PER_SAMPLE
    if n <= 0:
        return []
    # struct.unpack on large buffers is fine for VOD-length at 8 kHz.
    return list(struct.unpack(f"<{n}f", raw[: n * _BYTES_PER_SAMPLE]))


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    acc = 0.0
    for s in samples:
        acc += s * s
    return math.sqrt(acc / len(samples))
