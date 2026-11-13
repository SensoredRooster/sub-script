"""Brand package model: migration, upsert, selection modes, performance learning."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from subscript import brand_packages as bp


def test_legacy_config_migrates_to_default_package() -> None:
    cfg = {
        "brand": {"logo_path": "assets/logo.png", "position": "top_left", "opacity": 0.5},
        "captions": {"enabled": False, "engine": "whisper"},
        "music": {"enabled": True, "path": "assets/music.mp3", "volume": 0.2},
    }
    pkgs = bp.ensure_packages(cfg)
    assert len(pkgs) == 1
    pkg = pkgs[0]
    assert pkg["id"] == "default"
    assert pkg["brand"]["position"] == "top_left"
    assert pkg["captions"] == {"enabled": False, "engine": "whisper"}
    assert pkg["music"]["volume"] == 0.2
    # Idempotent
    assert bp.ensure_packages(cfg) is pkgs


def test_save_upserts_by_id() -> None:
    cfg: dict = {}
    bp.ensure_packages(cfg)
    pkg = bp.save_package(cfg, {"name": "Neon", "brand": {}, "captions": {}, "music": {}})
    assert pkg["id"]
    pkg["name"] = "Neon v2"
    bp.save_package(cfg, pkg)
    names = [p["name"] for p in bp.get_packages(cfg)]
    assert names == ["Default", "Neon v2"]


def test_delete_keeps_at_least_one_and_repins() -> None:
    cfg: dict = {}
    bp.ensure_packages(cfg)
    with pytest.raises(ValueError):
        bp.delete_package(cfg, "default")
    pkg = bp.save_package(cfg, {"name": "B", "brand": {}, "captions": {}, "music": {}})
    bp.set_selection(cfg, "pinned", pkg["id"])
    bp.delete_package(cfg, pkg["id"])
    assert bp.get_selection(cfg)["pinned_id"] == "default"


def test_selection_validation() -> None:
    cfg: dict = {}
    bp.ensure_packages(cfg)
    with pytest.raises(ValueError):
        bp.set_selection(cfg, "pinned", "nope")
    with pytest.raises(ValueError):
        bp.set_selection(cfg, "chaos")
    bp.set_selection(cfg, "auto", "default")
    assert bp.get_selection(cfg) == {"mode": "auto", "pinned_id": "default"}


def test_pinned_selection_always_returns_pinned() -> None:
    cfg: dict = {}
    bp.ensure_packages(cfg)
    other = bp.save_package(cfg, {"name": "B", "brand": {}, "captions": {}, "music": {}})
    bp.set_selection(cfg, "pinned", other["id"])
    for _ in range(5):
        assert bp.select_package(cfg)["id"] == other["id"]


def test_auto_rotates_round_robin(tmp_path: Path) -> None:
    cfg: dict = {}
    bp.ensure_packages(cfg)
    b = bp.save_package(cfg, {"name": "B", "brand": {}, "captions": {}, "music": {}})
    bp.set_selection(cfg, "auto", "default")
    first = bp.select_package(cfg, out_dir=tmp_path)
    second = bp.select_package(cfg, out_dir=tmp_path)
    third = bp.select_package(cfg, out_dir=tmp_path)
    assert first["id"] == "default"
    assert second["id"] == b["id"]
    assert third["id"] == "default"


def test_performance_weighting_favors_winner(tmp_path: Path) -> None:
    cfg: dict = {}
    bp.ensure_packages(cfg)
    b = bp.save_package(cfg, {"name": "B", "brand": {}, "captions": {}, "music": {}})
    bp.set_selection(cfg, "auto", "default")
    perf = {
        "default": {"clips": 5, "avg_views": 10.0},
        b["id"]: {"clips": 5, "avg_views": 1000.0},
    }
    rng = random.Random(42)
    wins = sum(
        bp.select_package(cfg, out_dir=tmp_path, perf=perf, rng=rng)["id"] == b["id"]
        for _ in range(200)
    )
    # 75% exploit share almost all goes to the 1000-view package.
    assert wins > 140


def test_overlay_replaces_brand_captions_music() -> None:
    cfg = {"brand": {"position": "top_left"}, "captions": {"enabled": True}, "other": 1}
    pkg = {
        "id": "x",
        "brand": {"position": "bottom_right", "logo_path": "assets/packages/x/logo.png"},
        "captions": {"enabled": False, "engine": "demo"},
        "music": {"enabled": True, "path": "assets/packages/x/music.mp3", "volume": 0.2},
    }
    out = bp.package_overlay(cfg, pkg)
    assert out["brand"]["position"] == "bottom_right"
    assert out["captions"]["engine"] == "demo"
    assert out["music"]["volume"] == 0.2
    assert out["other"] == 1
    assert cfg["brand"]["position"] == "top_left"  # original untouched


def test_package_summary_mentions_slots() -> None:
    pkg = {
        "brand": {"logo_path": "a", "intro_paths": ["i1", "i2"], "outro_paths": ["o1"]},
        "captions": {"enabled": True, "engine": "auto"},
        "music": {"enabled": True, "path": "m"},
    }
    text = bp.package_summary(pkg)
    assert "2 intros" in text and "1 outro" in text and "music bed" in text
