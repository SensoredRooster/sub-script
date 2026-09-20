from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"
EXAMPLE_CONFIG = ROOT / "config.example.yaml"
ASSETS_DIR = ROOT / "assets"
DEFAULT_LOGO_REL = "assets/logo.png"


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if not cfg_path.exists():
        if path is not None:
            raise SystemExit(
                f"Config not found: {cfg_path}\n"
                "  Windows: copy config.example.yaml config.yaml\n"
                "  macOS/Linux: cp config.example.yaml config.yaml"
            )
        if not EXAMPLE_CONFIG.exists():
            raise SystemExit(
                f"Neither config.yaml nor config.example.yaml found under {ROOT}"
            )
        raise SystemExit(
            "config.yaml not found.\n"
            "  Windows: copy config.example.yaml config.yaml\n"
            "  macOS/Linux: cp config.example.yaml config.yaml\n"
            "  Then edit config.yaml if you need different paths or ports."
        )
    with cfg_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Env overrides
    if os.getenv("SUB_SCRIPT_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        data.setdefault("youtube", {})["enabled"] = False
    return data


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
