"""Branding panel helpers and FastAPI route registration (logo + captions + music)."""

from __future__ import annotations

import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from subscript.captions import whisper_available
from subscript.config import ASSETS_DIR, DEFAULT_LOGO_REL, ROOT, save_config, update_brand_settings
from subscript.config_polish import (
    DEFAULT_MUSIC_REL,
    resolve_music_asset,
    update_captions_settings,
    update_music_settings,
)
from subscript.default_brand import ensure_default_logo

_BRAND_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")
_BRAND_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_SNIPPETS = Path(__file__).resolve().parent / "static" / "snippets"


def resolve_logo_path(brand: dict[str, Any]) -> Path | None:
    ensure_default_logo(ROOT)
    raw = (brand.get("logo_path") or DEFAULT_LOGO_REL or "").strip()
    if not raw:
        raw = DEFAULT_LOGO_REL
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path if path.is_file() else None


def branding_html(brand: dict[str, Any], snip: Callable[[str], str], cfg: dict[str, Any] | None = None) -> str:
    ensure_default_logo(ROOT)
    cfg = cfg or {}
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

    caps = cfg.get("captions") if isinstance(cfg.get("captions"), dict) else {}
    caps_on = True if "enabled" not in caps else bool(caps.get("enabled"))
    engine = str((caps or {}).get("engine") or "auto").strip().lower()
    if engine not in ("auto", "demo", "whisper"):
        engine = "auto"

    music = cfg.get("music") if isinstance(cfg.get("music"), dict) else {}
    music_on = True if "enabled" not in music else bool(music.get("enabled"))
    try:
        mvol = float(music.get("volume") if music.get("volume") is not None else 0.10)
    except (TypeError, ValueError):
        mvol = 0.10
    mvol = max(0.01, min(0.35, mvol))
    has_music = resolve_music_asset(cfg) is not None
    if has_music:
        music_status = f"Bed ready: {music.get('path') or DEFAULT_MUSIC_REL}"
    else:
        music_status = "No music file yet — upload an MP3 or drop assets/music.mp3 (mix skipped until then)."

    if whisper_available():
        whisper_hint = "faster-whisper is installed — Auto / Whisper can generate real timed captions."
    else:
        whisper_hint = (
            "faster-whisper not installed — Auto/Whisper fall back to demo SRT. "
            "Optional: pip install -r requirements-whisper.txt"
        )

    def sel(key: str) -> str:
        return "selected" if position == key else ""

    def eng(key: str) -> str:
        return "selected" if engine == key else ""

    def sequence_status(key: str, label: str) -> str:
        raw = brand.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        count = len(raw) if isinstance(raw, list) else 0
        return f"{count} {label} ready — one is chosen for each new clip." if count else f"No {label.lower()} yet — optional."

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
        .replace("{{CAPS_ENABLED}}", "checked" if caps_on else "")
        .replace("{{ENG_AUTO}}", eng("auto"))
        .replace("{{ENG_DEMO}}", eng("demo"))
        .replace("{{ENG_WHISPER}}", eng("whisper"))
        .replace("{{WHISPER_HINT}}", whisper_hint)
        .replace("{{MUSIC_ENABLED}}", "checked" if music_on else "")
        .replace("{{MUSIC_STATUS}}", music_status)
        .replace("{{MUSIC_VOLUME}}", f"{mvol:.2f}")
        .replace("{{INTRO_STATUS}}", sequence_status("intro_paths", "intro clips"))
        .replace("{{OUTRO_STATUS}}", sequence_status("outro_paths", "outro clips"))
    )


def register_branding_routes(app: FastAPI, cfg: dict[str, Any]) -> None:
    ensure_default_logo(ROOT)
    brand = cfg.setdefault("brand", {})
    if not (brand.get("logo_path") or "").strip():
        brand["logo_path"] = DEFAULT_LOGO_REL
    cfg.setdefault("captions", {"enabled": True, "engine": "auto"})
    cfg.setdefault(
        "music",
        {"enabled": True, "path": DEFAULT_MUSIC_REL, "volume": 0.10},
    )

    @app.get("/api/brand")
    def get_brand() -> JSONResponse:
        brand = dict(cfg.get("brand") or {})
        logo = resolve_logo_path(brand)
        caps = dict(cfg.get("captions") or {})
        music = dict(cfg.get("music") or {})
        return JSONResponse(
            {
                "logo_path": brand.get("logo_path") or DEFAULT_LOGO_REL,
                "position": brand.get("position") or "bottom_right",
                "opacity": float(brand.get("opacity") if brand.get("opacity") is not None else 0.85),
                "margin_px": int(brand.get("margin_px") if brand.get("margin_px") is not None else 24),
                "has_logo": logo is not None,
                "logo_url": "/brand/logo" if logo else None,
                "captions_enabled": bool(caps.get("enabled", True)),
                "captions_engine": str(caps.get("engine") or "auto"),
                "whisper_available": whisper_available(),
                "music_enabled": bool(music.get("enabled", True)),
                "music_path": music.get("path") or DEFAULT_MUSIC_REL,
                "music_volume": float(music.get("volume") if music.get("volume") is not None else 0.10),
                "has_music": resolve_music_asset(cfg) is not None,
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
        music: UploadFile | None = File(None),
        intros: list[UploadFile] = File(default=[]),
        outros: list[UploadFile] = File(default=[]),
        position: str = Form("bottom_right"),
        opacity: str = Form("0.85"),
        margin_px: str = Form("24"),
        captions_enabled: str | None = Form(None),
        captions_engine: str = Form("auto"),
        music_enabled: str | None = Form(None),
        music_volume: str = Form("0.10"),
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

            def save_video_variants(files: list[UploadFile], folder: str, key: str) -> None:
                if not files:
                    return
                target_dir = ASSETS_DIR / folder
                target_dir.mkdir(parents=True, exist_ok=True)
                existing = list((cfg.get("brand") or {}).get(key) or [])
                for upload in files:
                    if not upload or not upload.filename:
                        continue
                    suffix = Path(upload.filename).suffix.lower()
                    if suffix not in _BRAND_VIDEO_SUFFIXES:
                        raise ValueError(f"{folder[:-1].capitalize()} clips must be MP4, MOV, MKV, WebM, AVI, or M4V.")
                    safe = re.sub(r"[^\w.\-]+", "_", Path(upload.filename).stem)[:80] or "clip"
                    dest = target_dir / f"{safe}{suffix}"
                    with dest.open("wb") as out:
                        shutil.copyfileobj(upload.file, out)
                    if dest.stat().st_size == 0:
                        dest.unlink(missing_ok=True)
                        raise ValueError(f"Uploaded {folder[:-1]} was empty.")
                    rel = f"assets/{folder}/{dest.name}"
                    if rel not in existing:
                        existing.append(rel)
                cfg.setdefault("brand", {})[key] = existing

            save_video_variants(intros, "intros", "intro_paths")
            save_video_variants(outros, "outros", "outro_paths")
            save_config(cfg)

            # HTML checkboxes omit the field when unchecked.
            caps_on = captions_enabled is not None and str(captions_enabled).strip() not in (
                "",
                "0",
                "false",
                "off",
            )
            update_captions_settings(
                cfg,
                enabled=caps_on,
                engine=(captions_engine or "auto").strip().lower(),
            )

            music_on = music_enabled is not None and str(music_enabled).strip() not in (
                "",
                "0",
                "false",
                "off",
            )
            try:
                mvol = float(music_volume)
            except (TypeError, ValueError) as exc:
                raise ValueError("Music volume must be a number between 0.01 and 0.35.") from exc

            music_rel: str | None = None
            if music is not None and music.filename:
                suffix = Path(music.filename).suffix.lower()
                ctype = (music.content_type or "").lower()
                ok_audio = suffix in {".mp3", ".m4a", ".aac", ".wav", ".ogg"} or any(
                    x in ctype for x in ("mpeg", "mp3", "audio")
                )
                if not ok_audio:
                    raise ValueError("Music must be an audio file (MP3 recommended).")
                ASSETS_DIR.mkdir(parents=True, exist_ok=True)
                # Normalize to music.mp3 for simple config path (ffmpeg accepts container).
                dest_m = ASSETS_DIR / ("music" + (suffix if suffix else ".mp3"))
                if suffix not in {".mp3", ".m4a", ".aac", ".wav", ".ogg"}:
                    dest_m = ASSETS_DIR / "music.mp3"
                with dest_m.open("wb") as out:
                    shutil.copyfileobj(music.file, out)
                if dest_m.stat().st_size == 0:
                    dest_m.unlink(missing_ok=True)
                    raise ValueError("Uploaded music was empty.")
                music_rel = f"assets/{dest_m.name}"

            update_music_settings(
                cfg,
                enabled=music_on,
                path=music_rel,
                volume=mvol,
            )
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/?err={quote(str(exc), safe='')}", status_code=303)
        return RedirectResponse(
            "/clip?msg="
            + quote(
                "Saved — logo, captions, and music settings apply to new clips.",
                safe="",
            ),
            status_code=303,
        )
