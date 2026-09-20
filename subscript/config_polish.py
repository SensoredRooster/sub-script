"""Persist captions + music toggles from the app UI into config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.config import DEFAULT_CONFIG, ROOT, save_config

DEFAULT_MUSIC_REL = "assets/music.mp3"
_VALID_ENGINES = frozenset({"auto", "demo", "whisper"})


def update_captions_settings(
    cfg: dict[str, Any],
    *,
    enabled: bool | None = None,
    engine: str | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Merge captions fields, persist, return captions dict."""
    caps = dict(cfg.get("captions") or {})
    if enabled is not None:
        caps["enabled"] = bool(enabled)
    if engine is not None:
        eng = str(engine).strip().lower()
        if eng not in _VALID_ENGINES:
            raise ValueError("Captions engine must be auto, demo, or whisper.")
        caps["engine"] = eng
    cfg["captions"] = caps
    save_config(cfg, config_path or DEFAULT_CONFIG)
    return caps


def update_music_settings(
    cfg: dict[str, Any],
    *,
    enabled: bool | None = None,
    path: str | None = None,
    volume: float | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Merge music fields, persist, return music dict."""
    music = dict(cfg.get("music") or {})
    if enabled is not None:
        music["enabled"] = bool(enabled)
    if path is not None:
        music["path"] = path
    if volume is not None:
        vol = float(volume)
        if not 0.01 <= vol <= 0.35:
            raise ValueError("Music volume must be between 0.01 and 0.35 (keeps bed quiet).")
        music["volume"] = vol
    if "path" not in music or not str(music.get("path") or "").strip():
        music["path"] = DEFAULT_MUSIC_REL
    cfg["music"] = music
    save_config(cfg, config_path or DEFAULT_CONFIG)
    return music


def resolve_music_asset(cfg: dict[str, Any] | None) -> Path | None:
    rel = DEFAULT_MUSIC_REL
    if cfg and isinstance(cfg.get("music"), dict):
        raw = (cfg["music"].get("path") or "").strip()
        if raw:
            rel = raw
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path if path.is_file() and path.stat().st_size > 0 else None
