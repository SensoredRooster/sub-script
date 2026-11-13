"""Branding panel helpers and FastAPI routes — brand package library.

A package bundles logo + captions + music + intro/outro. The page lists all
packages, controls how the pipeline picks one per clip (pinned / auto), and
hosts the package editor. The legacy ``POST /brand`` endpoint still works and
writes through to the pinned package so old links and tests keep behaving.
"""

from __future__ import annotations

import html as _html
import mimetypes
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from urllib.parse import quote

from subscript.analytics import performance_by, performance_summary, refresh_stats
from subscript.brand_packages import (
    delete_package,
    ensure_packages,
    get_package,
    get_packages,
    get_selection,
    package_summary,
    save_package,
    set_selection,
)
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
_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".ogg"}
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


def _resolve_rel(raw: str | None) -> Path | None:
    if not raw or not str(raw).strip():
        return None
    path = Path(str(raw))
    if not path.is_absolute():
        path = ROOT / path
    return path if path.is_file() else None


def _esc(text: Any) -> str:
    return _html.escape(str(text), quote=True)


def _package_cards(cfg: dict[str, Any], out_dir: Path | None) -> str:
    perf = performance_by(out_dir, "package_id") if out_dir else {}
    cards = []
    for pkg in get_packages(cfg):
        pid = _esc(pkg.get("id"))
        stats = perf.get(str(pkg.get("id")))
        perf_line = (
            f"Avg {stats['avg_views']:.0f} views across {stats['clips']} published clip"
            + ("s" if stats["clips"] != 1 else "")
            if stats
            else "No performance data yet"
        )
        cards.append(
            '<div class="control-panel package-card">'
            f"<h3>{_esc(pkg.get('name') or 'Package')}</h3>"
            f'<p class="meta">{_esc(package_summary(pkg))}</p>'
            f'<p class="meta perf">{_esc(perf_line)}</p>'
            '<div class="package-actions">'
            f'<a class="secondary" href="/clip?panel=style&edit={pid}#style">Edit</a>'
            '<form method="post" action="/brand/packages/delete" class="inline-form" '
            "onsubmit=\"return confirm('Delete this package? Clips already made keep their look.');\">"
            f'<input type="hidden" name="package_id" value="{pid}">'
            '<button type="submit" class="link-danger">Delete</button>'
            "</form></div></div>"
        )
    cards.append(
        '<div class="control-panel package-card package-card-new">'
        "<h3>New package</h3>"
        '<p class="meta">Bundle a different look: logo, intro/outro, music, captions.</p>'
        '<div class="package-actions"><a class="primary" href="/clip?panel=style&edit=new#style">Create package</a></div></div>'
    )
    return "".join(cards)


def branding_html(
    brand: dict[str, Any],
    snip: Callable[[str], str],
    cfg: dict[str, Any] | None = None,
    *,
    edit_id: str = "",
    out_dir: Path | None = None,
) -> str:
    ensure_default_logo(ROOT)
    cfg = cfg or {}
    ensure_packages(cfg)

    # Which package is the editor showing?
    pkg: dict[str, Any] | None = None
    if edit_id and edit_id != "new":
        pkg = get_package(cfg, edit_id)
    if pkg is None and not edit_id:
        pkg = get_package(cfg, get_selection(cfg)["pinned_id"])
    editing_new = edit_id == "new"

    pkg_brand = (pkg or {}).get("brand") or {}
    pkg_caps = (pkg or {}).get("captions") or {}
    pkg_music = (pkg or {}).get("music") or {}

    logo = _resolve_rel(pkg_brand.get("logo_path")) if pkg else resolve_logo_path(brand)
    position = pkg_brand.get("position") or "bottom_right"
    if position not in _BRAND_POSITIONS:
        position = "bottom_right"
    try:
        opacity = float(pkg_brand.get("opacity") if pkg_brand.get("opacity") is not None else 0.85)
    except (TypeError, ValueError):
        opacity = 0.85
    opacity = max(0.1, min(1.0, opacity))
    try:
        margin = int(pkg_brand.get("margin_px") if pkg_brand.get("margin_px") is not None else 24)
    except (TypeError, ValueError):
        margin = 24

    caps_on = bool(pkg_caps.get("enabled", True))
    engine = str(pkg_caps.get("engine") or "auto").strip().lower()
    if engine not in ("auto", "demo", "whisper"):
        engine = "auto"

    music_on = bool(pkg_music.get("enabled", True))
    try:
        mvol = float(pkg_music.get("volume") if pkg_music.get("volume") is not None else 0.10)
    except (TypeError, ValueError):
        mvol = 0.10
    mvol = max(0.01, min(0.35, mvol))
    music_path = _resolve_rel(pkg_music.get("path"))
    music_status = (
        f"Bed ready: {pkg_music.get('path')}" if music_path
        else "No music file yet — upload an MP3 (mix skipped until then)."
    )

    if whisper_available():
        whisper_hint = "Speech transcription is installed — captions will use your real audio."
    else:
        whisper_hint = (
            "Speech transcription is not in this build, so clips are exported without captions. "
            "Nothing fake is ever burned in — the demo engine is only for trying the look."
        )

    def sel(key: str) -> str:
        return "selected" if position == key else ""

    def eng(key: str) -> str:
        return "selected" if engine == key else ""

    def sequence_status(key: str, label: str) -> str:
        raw = pkg_brand.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        count = len(raw) if isinstance(raw, list) else 0
        return f"{count} {label} ready — one is chosen for each new clip." if count else f"No {label.lower()} yet — optional."

    selection = get_selection(cfg)
    pinned_options = "".join(
        f'<option value="{_esc(p["id"])}" {"selected" if p["id"] == selection["pinned_id"] else ""}>'
        f'{_esc(p.get("name") or "Package")}</option>'
        for p in get_packages(cfg)
    )
    try:
        summary = performance_summary(out_dir) if out_dir else ""
    except Exception:
        summary = ""

    logo_src = ""
    if logo:
        logo_src = f"/brand/packages/{pkg['id']}/logo" if pkg else "/brand/logo"

    html = snip("branding.html")
    return (
        html.replace("{{MODE_AUTO}}", "checked" if selection["mode"] == "auto" else "")
        .replace("{{MODE_PINNED}}", "checked" if selection["mode"] == "pinned" else "")
        .replace("{{PINNED_OPTIONS}}", pinned_options)
        .replace("{{PERF_SUMMARY}}", _esc(summary))
        .replace("{{PACKAGE_CARDS}}", _package_cards(cfg, out_dir))
        .replace("{{PACKAGE_ID}}", "" if editing_new else _esc((pkg or {}).get("id", "")))
        .replace("{{PACKAGE_NAME}}", _esc((pkg or {}).get("name", "")) if not editing_new else "")
        .replace("{{EDITOR_HEADING}}", "Create a package" if editing_new else f"Edit package: {_esc((pkg or {}).get('name', 'Default'))}")
        .replace("{{SAVE_LABEL}}", "Create package" if editing_new else "Save package")
        .replace("{{PREVIEW_HIDDEN}}", "" if logo else "hidden")
        .replace("{{EMPTY_HIDDEN}}", "hidden" if logo else "")
        .replace("{{LOGO_SRC}}", logo_src)
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


def _checked(value: str | None) -> bool:
    return value is not None and str(value).strip().lower() not in ("", "0", "false", "off")


def _pkg_asset_dir(package_id: str) -> Path:
    return ASSETS_DIR / "packages" / package_id


async def _save_pkg_logo(logo: UploadFile | None, package_id: str) -> str | None:
    if logo is None or not logo.filename:
        return None
    suffix = Path(logo.filename).suffix.lower()
    ctype = (logo.content_type or "").lower()
    if suffix != ".png" and "png" not in ctype:
        raise ValueError("Logo must be a PNG file.")
    dest_dir = _pkg_asset_dir(package_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "logo.png"
    with dest.open("wb") as out:
        shutil.copyfileobj(logo.file, out)
    if dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise ValueError("Uploaded logo was empty.")
    return f"assets/packages/{package_id}/logo.png"


async def _save_pkg_music(music: UploadFile | None, package_id: str) -> str | None:
    if music is None or not music.filename:
        return None
    suffix = Path(music.filename).suffix.lower()
    ctype = (music.content_type or "").lower()
    if suffix not in _AUDIO_SUFFIXES and not any(x in ctype for x in ("mpeg", "mp3", "audio")):
        raise ValueError("Music must be an audio file (MP3 recommended).")
    dest_dir = _pkg_asset_dir(package_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / ("music" + (suffix if suffix in _AUDIO_SUFFIXES else ".mp3"))
    with dest.open("wb") as out:
        shutil.copyfileobj(music.file, out)
    if dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise ValueError("Uploaded music was empty.")
    return f"assets/packages/{package_id}/{dest.name}"


async def _save_pkg_videos(
    files: list[UploadFile], package_id: str, folder: str, existing: list[str]
) -> list[str]:
    if not files:
        return existing
    target_dir = _pkg_asset_dir(package_id) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
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
        rel = f"assets/packages/{package_id}/{folder}/{dest.name}"
        if rel not in existing:
            existing.append(rel)
    return existing


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
    ensure_packages(cfg)

    def _out_dir() -> Path:
        return Path((cfg.get("output") or {}).get("dir") or "out")

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
                "packages": [
                    {"id": p.get("id"), "name": p.get("name"), "summary": package_summary(p)}
                    for p in get_packages(cfg)
                ],
                "selection": get_selection(cfg),
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

    @app.get("/brand/packages/{package_id}/logo")
    def package_logo(package_id: str) -> FileResponse:
        pkg = get_package(cfg, package_id)
        if not pkg:
            raise HTTPException(404, "Unknown package")
        logo = _resolve_rel((pkg.get("brand") or {}).get("logo_path"))
        if not logo:
            raise HTTPException(404, "Package has no logo")
        mime, _ = mimetypes.guess_type(str(logo))
        return FileResponse(logo, media_type=mime or "image/png")

    @app.post("/brand/selection")
    def save_selection(mode: str = Form("pinned"), pinned_id: str = Form("")) -> RedirectResponse:
        try:
            set_selection(cfg, mode, pinned_id or None)
            save_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/clip?panel=style&err={quote(str(exc), safe='')}#style", status_code=303)
        return RedirectResponse(
            "/clip?panel=style&msg=" + quote("Saved — package picking preference updated.", safe="") + "#style",
            status_code=303,
        )

    @app.post("/brand/packages/delete")
    def remove_package(package_id: str = Form(...)) -> RedirectResponse:
        try:
            delete_package(cfg, package_id)
            save_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/clip?panel=style&err={quote(str(exc), safe='')}#style", status_code=303)
        return RedirectResponse(
            "/clip?panel=style&msg=" + quote("Package deleted.", safe="") + "#style",
            status_code=303,
        )

    @app.post("/brand/refresh-stats")
    def refresh() -> RedirectResponse:
        result = refresh_stats(cfg, _out_dir())
        if result.get("error"):
            return RedirectResponse(
                f"/clip?panel=style&err={quote(result['error'], safe='')}#style", status_code=303
            )
        msg = f"Stats refreshed for {result['updated']} of {result['clips']} tracked clips."
        return RedirectResponse(
            f"/clip?panel=style&msg={quote(msg, safe='')}#style", status_code=303
        )

    @app.post("/brand/packages")
    async def save_pkg(
        package_id: str = Form(""),
        package_name: str = Form(""),
        logo: UploadFile | None = File(None),
        music: UploadFile | None = File(None),
        intros: list[UploadFile] = File(default=[]),
        outros: list[UploadFile] = File(default=[]),
        clear_intros: str | None = Form(None),
        clear_outros: str | None = Form(None),
        position: str = Form("bottom_right"),
        opacity: str = Form("0.85"),
        margin_px: str = Form("24"),
        captions_enabled: str | None = Form(None),
        captions_engine: str = Form("auto"),
        music_enabled: str | None = Form(None),
        music_volume: str = Form("0.10"),
    ) -> RedirectResponse:
        try:
            existing = get_package(cfg, package_id) if package_id else None
            if package_id and not existing:
                raise ValueError("Unknown package.")
            pid = package_id or uuid.uuid4().hex[:8]
            name = (package_name or "").strip()
            if not name:
                raise ValueError("Give the package a name.")

            pos = (position or "bottom_right").strip()
            if pos not in _BRAND_POSITIONS:
                raise ValueError("Position must be top_left, top_right, bottom_left, or bottom_right.")
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
            try:
                mvol = float(music_volume)
            except (TypeError, ValueError) as exc:
                raise ValueError("Music volume must be a number between 0.01 and 0.35.") from exc

            old_brand = (existing or {}).get("brand") or {}
            old_caps = (existing or {}).get("captions") or {}
            old_music = (existing or {}).get("music") or {}

            logo_rel = await _save_pkg_logo(logo, pid)
            music_rel = await _save_pkg_music(music, pid)

            intro_list = [] if _checked(clear_intros) else list(old_brand.get("intro_paths") or [])
            outro_list = [] if _checked(clear_outros) else list(old_brand.get("outro_paths") or [])
            intro_list = await _save_pkg_videos(intros, pid, "intros", intro_list)
            outro_list = await _save_pkg_videos(outros, pid, "outros", outro_list)

            pkg = {
                "id": pid,
                "name": name,
                "created": (existing or {}).get("created") or time.time(),
                "brand": {
                    "logo_path": logo_rel or old_brand.get("logo_path") or DEFAULT_LOGO_REL,
                    "position": pos,
                    "opacity": opacity_val,
                    "margin_px": margin_val,
                    "intro_paths": intro_list,
                    "outro_paths": outro_list,
                },
                "captions": {
                    "enabled": _checked(captions_enabled),
                    "engine": (captions_engine or "auto").strip().lower(),
                },
                "music": {
                    "enabled": _checked(music_enabled),
                    "path": music_rel or old_music.get("path") or DEFAULT_MUSIC_REL,
                    "volume": mvol,
                },
            }
            save_package(cfg, pkg)
            save_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/clip?panel=style&err={quote(str(exc), safe='')}#style", status_code=303)
        verb = "updated" if package_id else "created"
        return RedirectResponse(
            "/clip?panel=style&msg=" + quote(f"Package {verb} — it applies to new clips.", safe="") + "#style",
            status_code=303,
        )

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
        """Legacy single-brand save — writes through to the pinned package too."""
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

            caps_on = _checked(captions_enabled)
            update_captions_settings(
                cfg,
                enabled=caps_on,
                engine=(captions_engine or "auto").strip().lower(),
            )

            music_on = _checked(music_enabled)
            try:
                mvol = float(music_volume)
            except (TypeError, ValueError) as exc:
                raise ValueError("Music volume must be a number between 0.01 and 0.35.") from exc

            music_rel: str | None = None
            if music is not None and music.filename:
                suffix = Path(music.filename).suffix.lower()
                ctype = (music.content_type or "").lower()
                ok_audio = suffix in _AUDIO_SUFFIXES or any(
                    x in ctype for x in ("mpeg", "mp3", "audio")
                )
                if not ok_audio:
                    raise ValueError("Music must be an audio file (MP3 recommended).")
                ASSETS_DIR.mkdir(parents=True, exist_ok=True)
                dest_m = ASSETS_DIR / ("music" + (suffix if suffix else ".mp3"))
                if suffix not in _AUDIO_SUFFIXES:
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

            # Write through to the pinned package so the library stays in sync.
            pinned = get_package(cfg, get_selection(cfg)["pinned_id"])
            if pinned:
                pinned["brand"] = {
                    **(pinned.get("brand") or {}),
                    **{k: v for k, v in (cfg.get("brand") or {}).items() if k in (
                        "logo_path", "position", "opacity", "margin_px", "intro_paths", "outro_paths"
                    )},
                }
                pinned["captions"] = dict(cfg.get("captions") or {})
                pinned["music"] = dict(cfg.get("music") or {})
                save_package(cfg, pinned)
            save_config(cfg)
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/?err={quote(str(exc), safe='')}", status_code=303)
        return RedirectResponse(
            "/clip?panel=style&msg="
            + quote(
                "Saved — logo, captions, and music settings apply to new clips.",
                safe="",
            )
            + "#style",
            status_code=303,
        )
