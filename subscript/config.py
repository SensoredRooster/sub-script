from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"
EXAMPLE_CONFIG = ROOT / "config.example.yaml"


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
