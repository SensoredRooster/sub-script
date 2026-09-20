"""Branding panel helpers and FastAPI route registration."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from subscript.config import ASSETS_DIR, DEFAULT_LOGO_REL, ROOT, update_brand_settings

_BRAND_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")
_SNIPPETS = Path(__file__).resolve().parent / "static" / "snippets"


def resolve_logo_path(brand: dict[str, Any]) -> Path | None:
    raw = (brand.get("logo_path") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path if path.is_file() else None


def branding_html(brand: dict[str, Any], snip: Callable[[str], str]) -> str:
    logo = resolve_logo_path(brand)
    position = brand.get("position") or "bottom_right"
    if position not in _BRAND_POSITIONS:
        position = "bottom_right"
    try:
        opacity = float(brand.get("opacity") if brand.get("opacity") is not None else 0.85)
    except (TypeError, ValueError):
        opacity = 0.85
    opacity = max(0.1, min(1.0, opacity))
    try:
        margin = int(brand.get("margin_px") if brand.get("margin_px") is not None else 24)
    except (TypeError, ValueError):
        margin = 24

    def sel(key: str) -> str:
        return "selected" if position == key else ""

    html = snip("branding.html")
    return (
        html.replace("{{PREVIEW_HIDDEN}}", "" if logo else "hidden")
        .replace("{{EMPTY_HIDDEN}}", "hidden" if logo else "")
        .replace("{{LOGO_SRC}}", "/brand/logo" if logo else "")
        .replace("{{OPACITY}}", f"{opacity:g}")
        .replace("{{MARGIN}}", str(margin))
        .replace("{{POS_TL}}", sel("top_left"))
        .replace("{{POS_TR}}", sel("top_right"))
        .replace("{{POS_BL}}", sel("bottom_left"))
        .replace("{{POS_BR}}", sel("bottom_right"))
    )


def register_branding_routes(app: FastAPI, cfg: dict[str, Any]) -> None:
    @app.get("/api/brand")
    def get_brand() -> JSONResponse:
        brand = dict(cfg.get("brand") or {})
        logo = resolve_logo_path(brand)
        return JSONResponse(
            {
                "logo_path": brand.get("logo_path") or DEFAULT_LOGO_REL,
                "position": brand.get("position") or "bottom_right",
                "opacity": float(brand.get("opacity") if brand.get("opacity") is not None else 0.85),
                "margin_px": int(brand.get("margin_px") if brand.get("margin_px") is not None else 24),
                "has_logo": logo is not None,
                "logo_url": "/brand/logo" if logo else None,
            }
        )

    @app.get("/brand/logo")
    def brand_logo() -> FileResponse:
        logo = resolve_logo_path(cfg.get("brand") or {})
        if not logo:
            fallback = ROOT / DEFAULT_LOGO_REL
            if fallback.is_file():
                logo = fallback
            else:
                raise HTTPException(404, "No logo configured")
        mime, _ = mimetypes.guess_type(str(logo))
        return FileResponse(logo, media_type=mime or "image/png")

    @app.post("/brand")
    async def save_brand(
        logo: UploadFile | None = File(None),
        position: str = Form("bottom_right"),
        opacity: str = Form("0.85"),
        margin_px: str = Form("24"),
    ) -> RedirectResponse:
        try:
            pos = (position or "bottom_right").strip()
            if pos not in _BRAND_POSITIONS:
                raise ValueError(
                    "Position must be top_left, top_right, bottom_left, or bottom_right."
                )
            try:
                opacity_val = float(opacity)
            except (TypeError, ValueError) as exc:
                raise ValueError("Opacity must be a number between 0.1 and 1.") from exc
            if not 0.05 <= opacity_val <= 1.0:
                raise ValueError("Opacity must be between 0.1 and 1.")
            try:
                margin_val = int(float(margin_px))
            except (TypeError, ValueError) as exc:
                raise ValueError("Margin must be a whole number of pixels.") from exc
            if margin_val < 0 or margin_val > 400:
                raise ValueError("Margin must be between 0 and 400.")

            logo_rel: str | None = None
            if logo is not None and logo.filename:
                suffix = Path(logo.filename).suffix.lower()
                ctype = (logo.content_type or "").lower()
                if suffix != ".png" and "png" not in ctype:
                    raise ValueError("Logo must be a PNG file.")
                ASSETS_DIR.mkdir(parents=True, exist_ok=True)
                dest = ASSETS_DIR / "logo.png"
                with dest.open("wb") as out:
                    shutil.copyfileobj(logo.file, out)
                if dest.stat().st_size == 0:
                    dest.unlink(missing_ok=True)
                    raise ValueError("Uploaded logo was empty.")
                logo_rel = DEFAULT_LOGO_REL

            update_brand_settings(
                cfg,
                logo_path=logo_rel,
                position=pos,
                opacity=opacity_val,
                margin_px=margin_val,
            )
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/?err={quote(str(exc), safe='')}", status_code=303)
        return RedirectResponse(
            "/?msg=" + quote("Saved — new clips will use this logo.", safe=""),
            status_code=303,
        )
