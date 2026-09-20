"""Ensure a generic brand logo exists for first-run auto-branding."""
from __future__ import annotations

import base64
from pathlib import Path

_DEFAULT_LOGO_B64 = (
    "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"
)


def ensure_default_logo(root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parents[1]
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    logo = assets / "logo.png"
    if logo.exists() and logo.stat().st_size > 0:
        return logo
    logo.write_bytes(base64.b64decode("".join(_DEFAULT_LOGO_B64) if not isinstance(_DEFAULT_LOGO_B64, str) else _DEFAULT_LOGO_B64))
    return logo
