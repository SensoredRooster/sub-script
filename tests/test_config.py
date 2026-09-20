"""Config loading, .env handling, dry-run safety switch, and settings persistence."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from subscript import config as cfg_mod
from subscript import config_polish


def test_apply_env_overrides_forces_dry_run_on_both_switches(monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "1")
    data = {
        "youtube": {"enabled": True},
        "platforms": {"youtube": {"enabled": True}, "tiktok": {"enabled": True}},
    }
    out = cfg_mod.apply_env_overrides(data)
    assert out["youtube"]["enabled"] is False
    assert out["platforms"]["youtube"]["enabled"] is False
    assert out["platforms"]["tiktok"]["enabled"] is True
    assert cfg_mod.dry_run_forced() is True


def test_apply_env_overrides_respects_zero(monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    data = {"youtube": {"enabled": True}, "platforms": {"youtube": {"enabled": True}}}
    out = cfg_mod.apply_env_overrides(data)
    assert out["youtube"]["enabled"] is True
    assert out["platforms"]["youtube"]["enabled"] is True
    assert cfg_mod.dry_run_forced() is False


def test_apply_env_overrides_handles_missing_youtube_block(monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "yes")
    out = cfg_mod.apply_env_overrides({"youtube": None})
    assert out["youtube"] == {"enabled": False}


def test_load_dotenv_parses_quotes_and_never_overrides(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nSUBTEST_A=\"quoted value\"\nSUBTEST_B='single'\nSUBTEST_C=plain\n\nnot a pair\n",
        encoding="utf-8",
    )
    for key in ("SUBTEST_A", "SUBTEST_B"):
        monkeypatch.setenv(key, "tmp")
        monkeypatch.delenv(key)
    monkeypatch.setenv("SUBTEST_C", "keep-me")
    cfg_mod.load_dotenv(env)
    assert os.environ["SUBTEST_A"] == "quoted value"
    assert os.environ["SUBTEST_B"] == "single"
    assert os.environ["SUBTEST_C"] == "keep-me"


def test_load_dotenv_missing_file_is_noop(tmp_path: Path) -> None:
    cfg_mod.load_dotenv(tmp_path / "nope.env")


def test_load_config_explicit_path_and_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "1")
    path = tmp_path / "c.yaml"
    path.write_text("hotkey: ctrl+alt+c\nyoutube:\n  enabled: true\n", encoding="utf-8")
    data = cfg_mod.load_config(path)
    assert data["hotkey"] == "ctrl+alt+c"
    assert data["youtube"]["enabled"] is False


def test_load_config_explicit_missing_path_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cfg_mod.load_config(tmp_path / "missing.yaml")


def test_load_config_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cfg_mod.load_config(path)


def test_load_config_empty_file_is_empty_dict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert cfg_mod.load_config(path) == {}


def test_save_and_update_brand_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    cfg = {"brand": {"logo_path": "assets/logo.png", "opacity": 0.85}}
    brand = cfg_mod.update_brand_settings(
        cfg, position="top_left", opacity=0.5, margin_px=10, config_path=path
    )
    assert brand["position"] == "top_left"
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["brand"]["position"] == "top_left"
    assert saved["brand"]["opacity"] == 0.5
    assert saved["brand"]["margin_px"] == 10
    assert saved["brand"]["logo_path"] == "assets/logo.png"


def test_update_captions_settings_validates_engine(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    cfg: dict = {}
    caps = config_polish.update_captions_settings(cfg, enabled=False, engine="Demo", config_path=path)
    assert caps == {"enabled": False, "engine": "demo"}
    with pytest.raises(ValueError):
        config_polish.update_captions_settings(cfg, engine="bogus", config_path=path)


def test_update_music_settings_clamps_and_defaults_path(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    cfg: dict = {}
    music = config_polish.update_music_settings(cfg, enabled=True, volume=0.2, config_path=path)
    assert music["path"] == config_polish.DEFAULT_MUSIC_REL
    assert music["volume"] == 0.2
    with pytest.raises(ValueError):
        config_polish.update_music_settings(cfg, volume=0.9, config_path=path)
