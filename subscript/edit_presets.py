"""Preset editing styles for automatic clip selection.

Each preset tunes how SubScript picks moments from raw footage: how long a
clip runs and how the highlight scorer weighs excitement spikes vs. pacing.
The goal: raw content in, a clip that matches the creator's intent out.
"""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "hype": {
        "label": "Hype moments",
        "desc": "Short, explosive peaks — best for Shorts / TikTok / Reels.",
        "clip_seconds": 20.0,
        "top_n": 3,
        "weights": (0.65, 0.20, 0.15),
    },
    "balanced": {
        "label": "Balanced",
        "desc": "A bit of everything — strong moments with room to breathe.",
        "clip_seconds": 30.0,
        "top_n": 3,
        "weights": (0.55, 0.25, 0.20),
    },
    "story": {
        "label": "Story / talking",
        "desc": "Longer, steady segments — rants, stories, explanations.",
        "clip_seconds": 45.0,
        "top_n": 3,
        "weights": (0.35, 0.20, 0.45),
    },
}

DEFAULT_PRESET = "balanced"


def get_preset(name: str | None) -> dict[str, Any]:
    """Return the preset dict for ``name`` (falls back to balanced)."""
    key = str(name or "").strip().lower()
    preset = PRESETS.get(key, PRESETS[DEFAULT_PRESET])
    out = dict(preset)
    out["key"] = key if key in PRESETS else DEFAULT_PRESET
    return out
