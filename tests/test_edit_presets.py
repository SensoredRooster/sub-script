"""Edit preset definitions and fallback behavior."""

from __future__ import annotations

from subscript.edit_presets import DEFAULT_PRESET, PRESETS, get_preset


def test_default_preset_is_balanced() -> None:
    assert DEFAULT_PRESET == "balanced"
    p = get_preset(None)
    assert p["key"] == "balanced"
    assert p["clip_seconds"] == 30.0
    assert p["weights"] == (0.55, 0.25, 0.20)


def test_known_presets_have_consistent_shape() -> None:
    for key, preset in PRESETS.items():
        assert preset["label"]
        assert preset["desc"]
        assert preset["clip_seconds"] > 0
        assert preset["top_n"] >= 1
        assert len(preset["weights"]) == 3
        assert abs(sum(preset["weights"]) - 1.0) < 1e-6


def test_hype_and_story_differ_in_intent() -> None:
    hype = get_preset("hype")
    story = get_preset("story")
    assert hype["clip_seconds"] < story["clip_seconds"]
    assert hype["weights"][0] > story["weights"][0]  # hype favors spikes
    assert story["weights"][2] > hype["weights"][2]  # story favors sustain


def test_unknown_name_falls_back() -> None:
    assert get_preset("nonsense")["key"] == "balanced"
    assert get_preset("")["key"] == "balanced"
