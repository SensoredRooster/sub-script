from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from subscript.runtime_paths import app_dir, resource_dir

# Writable root: next to SubScript.exe when frozen, else repo root.
ROOT = app_dir()
DEFAULT_CONFIG = ROOT / "config.yaml"
EXAMPLE_CONFIG = ROOT / "config.example.yaml"
ASSETS_DIR = ROOT / "assets"
DEFAULT_LOGO_REL = "assets/logo.png"


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _example_config_path() -> Path:
    if EXAMPLE_CONFIG.exists():
        return EXAMPLE_CONFIG
    bundled = resource_dir() / "config.example.yaml"
    if bundled.exists():
        return bundled
    return EXAMPLE_CONFIG


def load_dotenv(path: Path | None = None) -> None:
    """Best-effort load of ``<app_dir>/.env`` into ``os.environ`` (no python-dotenv dep).

    Existing environment variables win over the file so a shell override still works.
    """
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


def dry_run_forced() -> bool:
    """True when ``SUB_SCRIPT_DRY_RUN`` (env or .env) forces YouTube upload off."""
    load_dotenv()
    return os.getenv("SUB_SCRIPT_DRY_RUN", "").strip().lower() in _TRUTHY


def apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply environment-driven safety overrides to a loaded config (in place)."""
    if dry_run_forced():
        yt = data.get("youtube")
        if not isinstance(yt, dict):
            yt = {}
            data["youtube"] = yt
        yt["enabled"] = False
        # platforms.youtube.enabled is the other switch for live Shorts upload.
        plats = data.get("platforms")
        if isinstance(plats, dict) and isinstance(plats.get("youtube"), dict):
            plats["youtube"]["enabled"] = False
    return data


def migrate_config(data: dict[str, Any]) -> dict[str, Any]:
    """Apply additive, in-memory defaults so old configs/profiles keep working."""
    data.setdefault("schema_version", 3)
    if not isinstance(data.get("automation_profiles"), list):
        data["automation_profiles"] = []
    for profile in data["automation_profiles"]:
        if not isinstance(profile, dict):
            continue
        # Old profiles intentionally remain center-crop until their owner chooses
        # a composer preset; this avoids changing an established workflow silently.
        profile.setdefault("vertical_layout", {"version": 1, "mode": "center_crop", "preset": "center_crop"})
    return data


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.exists():
        if path is not None:
            raise SystemExit(
                f"Config not found: {cfg_path}\n"
                "  Windows: copy config.example.yaml config.yaml\n"
                "  macOS/Linux: cp config.example.yaml config.yaml"
            )
        example = _example_config_path()
        if not example.exists():
            raise SystemExit(
                f"Neither config.yaml nor config.example.yaml found under {ROOT}"
            )
        # Frozen / first double-click: auto-create config beside the exe
        try:
            cfg_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Created {cfg_path.name} from example next to the app.")
        except OSError:
            raise SystemExit(
                "config.yaml not found.\n"
                "  Windows: copy config.example.yaml config.yaml\n"
                "  macOS/Linux: cp config.example.yaml config.yaml\n"
                "  Then edit config.yaml if you need different paths or ports."
            ) from None
    with cfg_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{cfg_path} must contain a YAML mapping (key: value lines).")
    applied = apply_env_overrides(data)
    return migrate_config(applied) if applied else applied


def save_config(data: dict[str, Any], path: Path | None = None) -> Path:
    """Write config.yaml (creates from current data)."""
    cfg_path = path or DEFAULT_CONFIG
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    return cfg_path


def update_brand_settings(
    cfg: dict[str, Any],
    *,
    logo_path: str | None = None,
    position: str | None = None,
    opacity: float | None = None,
    margin_px: int | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Merge brand fields into cfg, persist to config.yaml, return brand dict."""
    brand = dict(cfg.get("brand") or {})
    if logo_path is not None:
        brand["logo_path"] = logo_path
    if position is not None:
        brand["position"] = position
    if opacity is not None:
        brand["opacity"] = opacity
    if margin_px is not None:
        brand["margin_px"] = margin_px
    cfg["brand"] = brand
    save_config(cfg, config_path)
    return brand
