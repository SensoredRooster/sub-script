"""Suggest highlight windows from VOD audio dynamics (no ML).

Uses ffmpeg to sample mono PCM, builds a per-bucket loudness curve, then scores
sliding windows of ``buffer_seconds`` by *excitement relative to the VOD's own
baseline* — spikes above the channel's normal level, dynamics within the
window, and how much of the window stays engaged — instead of raw loudness.
Raw loudness alone picks constant music beds and menu noise; relative spikes
match what viewers actually react to. Fail-soft callers should catch errors
and fall back to last-N seconds.
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

# Default scoring weights: excitement spike / within-window dynamics / sustain.
_DEFAULT_WEIGHTS = (0.55, 0.25, 0.20)


def suggest_highlights(
    source: Path,
    *,
    buffer_seconds: float = 30.0,
    top_n: int = 5,
    hop_seconds: float | None = None,
    weights: tuple[float, float, float] | None = None,
) -> list[dict[str, Any]]:
    """Return top-N peak segments as ``{start, duration, score, reason}``.

    ``score`` is normalized 0..1 relative to the best window (1.0 = best).
    ``reason`` is a short human explanation of why the moment was picked.
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
    w = weights or _DEFAULT_WEIGHTS

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

    buckets, bucket_sec = _rms_buckets(samples, win_sec)
    baseline = _median(buckets)

    windows: list[tuple[float, float, float, float]] = []  # (score, start, duration, peak_ratio)

    def _add_window(start_s: float, n_samples: int) -> None:
        dur = n_samples / float(_SAMPLE_RATE)
        score, ratio = _window_score(buckets, bucket_sec, start_s, dur, baseline, w)
        windows.append((score, start_s, dur, ratio))

    if len(samples) <= win_samples:
        _add_window(0.0, len(samples))
    else:
        i = 0
        while i + win_samples <= len(samples):
            _add_window(i / float(_SAMPLE_RATE), win_samples)
            i += hop_samples
        # Ensure the final window that ends at EOF is considered.
        last_start_i = len(samples) - win_samples
        if last_start_i > 0 and (not windows or windows[-1][1] < last_start_i / _SAMPLE_RATE - 0.01):
            _add_window(last_start_i / _SAMPLE_RATE, win_samples)

    if not windows:
        raise RuntimeError("No analysis windows produced")

    # Best score first; break ties earlier in the VOD.
    windows.sort(key=lambda w_: (-w_[0], w_[1]))
    top = windows[0][0]
    if top <= 0 or math.isclose(top, 0.0):
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
                    "reason": "Evenly spaced guess (no clear audio peaks)",
                }
            )
        return out

    picked: list[dict[str, Any]] = []
    for score, start, dur, ratio in windows:
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
                "score": round(min(1.0, max(0.0, score / top)), 4),
                "reason": _reason(ratio),
            }
        )

    picked.sort(key=lambda p: float(p["start"]))
    return picked


def suggest_highlights_or_fallback(
    source: Path,
    *,
    buffer_seconds: float = 30.0,
    top_n: int = 5,
    cfg: dict[str, Any] | None = None,
    weights: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    """Analyze with fail-soft fallback to last ``buffer_seconds``.

    When ``cfg`` has ``detect.enabled`` and a player name, optionally merge
    experimental kill-feed timestamps (exact name match) with loudness peaks.
    Missing OCR engines or detect errors → loudness-only (fail-soft).

    Returns a payload suitable for ``POST /highlights`` JSON::

        {
          "suggestions": [...],
          "fallback": bool,
          "message": str,
          "buffer_seconds": float,
          "detect_note": str,   # optional kill-feed status
        }
    """
    buf = float(buffer_seconds)
    detect_note = ""
    try:
        suggestions = suggest_highlights(
            source, buffer_seconds=buf, top_n=top_n, weights=weights
        )
        for s in suggestions:
            s.setdefault("source", "loudness")
        suggestions, detect_note = _maybe_merge_killfeed(
            source, suggestions, buffer_seconds=buf, top_n=top_n, cfg=cfg
        )
        return {
            "suggestions": suggestions,
            "fallback": False,
            "message": "",
            "buffer_seconds": buf,
            "detect_note": detect_note,
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
            "detect_note": detect_note,
        }


def _maybe_merge_killfeed(
    source: Path,
    loudness: list[dict[str, Any]],
    *,
    buffer_seconds: float,
    top_n: int,
    cfg: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    """Kill-counter scan (default on) + optional kill-feed OCR; else unchanged.

    Kills always outrank loudness: counter hits get score 1.0 and sort first.
    Everything is fail-soft — missing engine or any error leaves loudness
    suggestions untouched and just adds a human-readable note.
    """
    try:
        from subscript.detect_killfeed import (
            detect_enabled,
            detect_kills,
            kills_to_suggestions,
            merge_highlight_suggestions,
            resolve_player_name,
        )
    except Exception as exc:  # noqa: BLE001
        return loudness, f"Kill-detect module unavailable ({exc})."

    det = cfg.get("detect") if isinstance(cfg, dict) and isinstance(cfg.get("detect"), dict) else {}
    mode = str(det.get("merge") or "merge").strip().lower()
    pre_roll = 8.0
    try:
        pre_roll = float(det.get("pre_roll") if det.get("pre_roll") is not None else 8.0)
    except (TypeError, ValueError):
        pre_roll = 8.0

    notes: list[str] = []

    # 1) Kill-counter scan — on by default, uses the bundled OCR engine,
    #    needs no player name. This is the primary "kills over everything" path.
    try:
        from subscript.kill_counter import detect_counter_kills, kill_counter_enabled

        if kill_counter_enabled(cfg):
            result = detect_counter_kills(source, cfg=cfg)
            kc_note = str(result.get("note") or "")
            if kc_note:
                notes.append(kc_note)
            kc_kills = list(result.get("kills") or [])
            if kc_kills:
                kc_sugs = kills_to_suggestions(
                    kc_kills, buffer_seconds=buffer_seconds, pre_roll=pre_roll
                )
                for s in kc_sugs:
                    s["source"] = "killcounter"
                loudness = merge_highlight_suggestions(
                    loudness, kc_sugs, top_n=top_n, mode=mode
                )
                notes.append(f"Kills first: merged {len(kc_kills)} kill-counter hit(s) ({mode}).")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Kill-counter skipped ({exc}); loudness-only.")

    # 2) Optional kill-feed name OCR (detect.enabled + player_name).
    if not detect_enabled(cfg):
        return loudness, " ".join(notes)
    name = resolve_player_name(cfg)
    if not name:
        notes.append("detect.enabled but player_name empty — kill-feed skipped.")
        return loudness, " ".join(notes)

    try:
        result = detect_kills(source, player_name=name, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Kill-feed skipped ({exc}); loudness-only.")
        return loudness, " ".join(notes)

    note = str(result.get("note") or "")
    kills = list(result.get("kills") or [])
    if not kills:
        notes.append(note or "No kill-feed hits (OCR missing or no exact name match).")
        return loudness, " ".join(notes)

    kill_sugs = kills_to_suggestions(
        kills, buffer_seconds=buffer_seconds, pre_roll=pre_roll
    )
    merged = merge_highlight_suggestions(
        loudness, kill_sugs, top_n=top_n, mode=mode
    )
    notes.append(f"Merged {len(kills)} kill-feed hit(s) ({mode}).")
    return merged, " ".join(n for n in notes if n)


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


def _rms_buckets(samples: list[float], win_sec: float) -> tuple[list[float], float]:
    """Per-bucket RMS loudness curve. Bucket ~1s, finer for short windows."""
    bucket_sec = max(0.25, min(1.0, win_sec / 4.0))
    step = max(1, int(round(bucket_sec * _SAMPLE_RATE)))
    buckets = [_rms(samples[i : i + step]) for i in range(0, len(samples), step)]
    return buckets, step / float(_SAMPLE_RATE)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile; good enough for bucket curves."""
    if not values:
        return 0.0
    s = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(s)))
    return s[min(len(s) - 1, rank - 1)]


def _window_score(
    buckets: list[float],
    bucket_sec: float,
    start_s: float,
    dur_s: float,
    baseline: float,
    weights: tuple[float, float, float],
) -> tuple[float, float]:
    """Score a window 0..1 by excitement relative to the VOD baseline.

    Components: spike (peak vs. the VOD's median loudness), dynamics (energy
    variation inside the window — constant music beds score low), sustain
    (share of the window above baseline). Returns (score, peak_ratio).
    """
    n = len(buckets)
    lo = max(0, int(start_s / bucket_sec))
    hi = min(n, max(lo + 1, int(round((start_s + dur_s) / bucket_sec))))
    wb = buckets[lo:hi]
    if not wb:
        return 0.0, 1.0
    mean_w = sum(wb) / len(wb)
    if mean_w <= 0:
        return 0.0, 1.0
    peak = _percentile(wb, 95.0)
    base = max(baseline, 1e-4)
    ratio = peak / base if base > 0 else 1.0
    spike = min(1.0, math.log2(max(1.0, ratio)) / 4.0)
    var = math.sqrt(sum((b - mean_w) ** 2 for b in wb) / len(wb))
    dyn = min(1.0, (var / mean_w) / 1.5)
    sustain = sum(1 for b in wb if b > base) / len(wb)
    w1, w2, w3 = weights
    return w1 * spike + w2 * dyn + w3 * sustain, ratio


def _reason(ratio: float) -> str:
    """Plain-language explanation of why a moment scored well."""
    if ratio >= 4.0:
        return f"Big energy spike — about {ratio:.0f}× your video's usual level"
    if ratio >= 2.0:
        return f"Clear excitement jump — about {ratio:.1f}× your video's usual level"
    if ratio >= 1.3:
        return "Noticeably more energetic than the rest of the video"
    return "Steady, consistent moment"
