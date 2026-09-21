"""App UI implementation (VOD clip + live hotkey + review)."""

from __future__ import annotations

import mimetypes
import re
import shutil
import uuid
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from subscript.branding_routes import branding_html, register_branding_routes
from subscript.capture_setup import setup_html, register_capture_setup
from subscript.config import dry_run_forced, load_config
from subscript.highlights import suggest_highlights_or_fallback
from subscript.hotkey import HotkeyWatcher
from subscript.live_app_actions import register_item_routes
from subscript.live_ui import live_card_html, register_live_routes
from subscript.pipeline import run_pipeline
from subscript.publishing_routes import publishing_html, register_publishing_routes
from subscript.queue import ReviewQueue
from subscript.post_metadata import editor_html
from subscript.runtime_paths import find_ffmpeg

_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_STATIC = Path(__file__).resolve().parent / "static"
_SNIPPETS = _STATIC / "snippets"
_YT_URL_RE = re.compile(
    r"https://(?:youtu\.be/[\w\-]+|www\.youtube\.com/(?:watch\?v=|shorts/)[\w\-]+)"
)


def _snip(name: str) -> str:
    return (_SNIPPETS / name).read_text(encoding="utf-8")


def _parse_time_field(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError as exc:
        raise ValueError(f"invalid time {value!r}; use seconds or HH:MM:SS") from exc
    raise ValueError(f"invalid time {value!r}; use seconds or HH:MM:SS")


def create_app(cfg: dict[str, Any] | None = None) -> FastAPI:
    cfg = cfg or load_config()
    out_dir = Path(cfg.get("output", {}).get("dir") or "out")
    uploads_dir = out_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    queue = ReviewQueue(out_dir / "review-queue.json")
    default_seconds = int(cfg.get("buffer_seconds") or 30)

    # Shared live watcher (background thread). Failures never crash the app.
    watcher_holder: dict[str, HotkeyWatcher | None] = {"w": None}

    app = FastAPI(title="sub-script")
    _STATIC.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    register_branding_routes(app, cfg)
    register_live_routes(app, cfg, watcher_holder)
    register_capture_setup(app, cfg, watcher_holder)
    register_publishing_routes(app, cfg)

    # A user who explicitly chose “Save & start automated workflow” should not need
    # to re-arm the global trigger after restarting the app.
    if cfg.get("auto_start_watcher"):
        try:
            from subscript.buffer import resolve_live_source
            from subscript.live_ui import ensure_watcher
            resolve_live_source(cfg)
            ensure_watcher(watcher_holder, cfg).start()
        except Exception as exc:  # noqa: BLE001 — app still opens so setup can be fixed
            print(f"Automated flow was saved but could not start: {exc}")

    @app.get("/", response_class=HTMLResponse)
    def home(msg: str | None = None, err: str | None = None) -> str:
        pending = queue.list(status="pending")
        rows = []
        card_tpl = _snip("card.html")
        for item in pending:
            captioned_ok = bool(item.vertical_captioned_path) and Path(
                item.vertical_captioned_path
            ).is_file()
            if captioned_ok:
                vert_variant = "captioned"
                vert_label = "Vertical 9:16 · captions burned in (this is what gets uploaded)"
                vert_extra = (
                    f'<p class="meta"><a href="/media/{_esc(item.id)}?variant=vertical" '
                    f'target="_blank" rel="noopener">Plain vertical (no captions)</a></p>'
                )
            else:
                vert_variant, vert_label, vert_extra = "vertical", "Vertical 9:16", ""
            trim_note = ""
            if item.trim_start is not None and item.trim_end is not None:
                trim_note = (
                    f"Trimmed {float(item.trim_start):g}s → {float(item.trim_end):g}s "
                    "from the master. "
                )
            trim_end_default = (
                float(item.trim_end) if item.trim_end is not None else float(default_seconds)
            )
            rows.append(
                card_tpl.replace("{{ID}}", _esc(item.id))
                .replace("{{TITLE}}", _esc(item.title))
                .replace("{{POST_COPY}}", editor_html(item))
                .replace("{{CREATED}}", _esc(item.created_at))
                .replace("{{VERT_VARIANT}}", vert_variant)
                .replace("{{VERT_LABEL}}", vert_label)
                .replace("{{VERT_EXTRA}}", vert_extra)
                .replace("{{TRIM_NOTE}}", _esc(trim_note))
                .replace("{{TRIM_END}}", f"{trim_end_default:g}")
            )
        review = "\n".join(rows) or _snip("empty.html")
        banner = ""
        if err:
            banner = f'<p class="banner bad-banner">{_esc(err)}</p>'
        elif msg:
            visible_msg = msg
            if msg.startswith("Approved — social pack"):
                visible_msg = "Approved — your finished files are saved. Nothing was uploaded because YouTube is off."
            elif msg.startswith("Trimmed - new horizontal"):
                visible_msg = "Your trimmed clip is ready. Watch it again, then approve it when happy."
            banner = f'<p class="banner ok-banner">{_esc(visible_msg)}</p>'
            m = _YT_URL_RE.search(msg)
            if m:
                url = m.group(0)
                banner += (
                    f'<p class="banner ok-banner">'
                    f'<a href="{_esc(url)}" target="_blank" rel="noopener">'
                    f"Open on YouTube</a></p>"
                )
        live = live_card_html(cfg, watcher_holder["w"], snip=_snip, esc=_esc)
        form = (
            _snip("clip_form.html")
            .replace("{{DEFAULT_SECONDS}}", str(default_seconds))
            .replace("{{LIVE_CARD}}", live)
        )
        branding = branding_html(cfg.get("brand") or {}, _snip, cfg)
        publishing = publishing_html(cfg, _snip)
        review_heading = "Your clip is ready" if pending else "Preview and approve"
        review_intro = (
            "Watch both previews, trim if you want, then approve the version you love."
            if pending
            else "Your clip will appear here after you choose a video above."
        )
        review_section = (
            '<section class="workflow-section" id="review">'
            '<div class="section-heading"><span class="step-number">4</span><div>'
            f'<p class="eyebrow">Review</p><h2>{review_heading}</h2>'
            f'<p>{review_intro}</p>'
            f'</div></div><div class="review-grid">{review}</div></section>'
        )
        body = banner + form + setup_html(cfg, _snip) + branding + review_section + publishing
        page = _snip("page.html").replace("{{BODY}}", body)
        if not (cfg.get("review") or {}).get("require_approval", True):
            page = page.replace("Review before publishing", "Automatic publishing on")
            page = page.replace("Review before publishing.", "Enabled destinations publish automatically.")
            page = page.replace("prepare both video formats for review.", "prepare both video formats for automatic delivery.")
        return page

    @app.post("/clip")
    async def make_clip(
        file: UploadFile | None = File(None),
        local_path: str = Form(""),
        mode: str = Form("last30"),
        start: str = Form(""),
        duration: str = Form(""),
    ) -> RedirectResponse:
        try:
            source = await _resolve_source(file, local_path, uploads_dir)
            if mode == "auto":
                highlights = suggest_highlights_or_fallback(
                    source, buffer_seconds=float(default_seconds), top_n=1, cfg=cfg
                )
                suggestions = highlights.get("suggestions") or []
                best = suggestions[0] if suggestions else {}
                clip_start = best.get("start")
                clip_duration = float(best.get("duration") or default_seconds)
            elif mode == "last30":
                clip_start: float | None = None
                clip_duration: float | None = float(default_seconds)
            else:
                clip_start = _parse_time_field(start)
                clip_duration = _parse_time_field(duration)
                if clip_start is None:
                    raise ValueError("Start time is required for a custom clip.")
                if clip_duration is None or clip_duration <= 0:
                    raise ValueError("Duration must be greater than zero.")
            run_pipeline(
                source, cfg, dry_run=bool((cfg.get("review") or {}).get("require_approval", True)), start=clip_start, duration=clip_duration
            )
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/?err={quote(str(exc), safe='')}", status_code=303)
        return RedirectResponse(
            "/?msg="
            + quote(
                ("Your clip is ready. Watch the previews below, then approve it when you like it. "
                 "Nothing is published before approval.")
                if (cfg.get("review") or {}).get("require_approval", True) else
                "Automatic processing complete. Export pack and publishing results are saved in out/approved. Only enabled live destinations upload; manual destinations create packs.",
                safe="",
            ) + ("#review" if (cfg.get("review") or {}).get("require_approval", True) else ""),
            status_code=303,
        )

    @app.post("/highlights")
    async def highlights(
        file: UploadFile | None = File(None),
        local_path: str = Form(""),
        top_n: str = Form("5"),
        buffer_seconds: str = Form(""),
    ) -> JSONResponse:
        """Analyze VOD loudness (+ optional kill-feed); return peak windows (fail-soft)."""
        try:
            source = await _resolve_source(file, local_path, uploads_dir)
        except Exception as exc:  # noqa: BLE001
            buf = float(default_seconds)
            return JSONResponse(
                {
                    "suggestions": [
                        {"start": None, "duration": buf, "score": 0.0}
                    ],
                    "fallback": True,
                    "message": (
                        f"Auto highlights failed ({exc}); "
                        f"falling back to last {default_seconds} seconds."
                    ),
                    "buffer_seconds": buf,
                }
            )
        try:
            n = int(float(top_n)) if str(top_n).strip() else 5
        except ValueError:
            n = 5
        if str(buffer_seconds).strip():
            try:
                buf = float(buffer_seconds)
            except ValueError:
                buf = float(default_seconds)
        else:
            buf = float(default_seconds)
        payload = suggest_highlights_or_fallback(
            source, buffer_seconds=buf, top_n=max(1, n), cfg=cfg
        )
        return JSONResponse(payload)

    @app.get("/media/{item_id}")
    def media(
        item_id: str,
        variant: str | None = Query(None),
    ) -> FileResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        path: Path | None = None
        if variant == "horizontal" and item.horizontal_path:
            path = Path(item.horizontal_path)
        elif variant == "vertical" and item.vertical_path:
            path = Path(item.vertical_path)
        elif variant == "captioned" and item.vertical_captioned_path:
            path = Path(item.vertical_captioned_path)
        else:
            path = Path(item.edited_path or item.video_path)
        if not path.exists():
            path = Path(item.edited_path or item.video_path)
        if not path.exists():
            raise HTTPException(404, "video missing")
        mime, _ = mimetypes.guess_type(str(path))
        return FileResponse(path, media_type=mime or "video/mp4")

    register_item_routes(app, cfg, queue, out_dir)

    return app


async def _resolve_source(
    file: UploadFile | None, local_path: str, uploads_dir: Path
) -> Path:
    path_text = (local_path or "").strip().strip('"')
    if path_text:
        path = Path(path_text)
        if not path.is_file():
            raise ValueError(f"File not found on this PC: {path}")
        if path.suffix.lower() not in _VIDEO_SUFFIXES:
            raise ValueError(f"Unsupported video type: {path.suffix or '(none)'}")
        return path.resolve()

    if file is None or not file.filename:
        raise ValueError("Drop or choose a video file, or paste a path on this PC.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _VIDEO_SUFFIXES:
        raise ValueError(f"Unsupported video type: {suffix or '(none)'}")

    safe_name = re.sub(r"[^\w.\-]+", "_", Path(file.filename).name)[:120]
    dest = uploads_dir / f"{uuid.uuid4().hex[:10]}_{safe_name}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return dest.resolve()


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main() -> None:
    import uvicorn

    cfg = load_config()
    host = cfg.get("review", {}).get("host", "127.0.0.1")
    port = int(cfg.get("review", {}).get("port", 8787))
    url = f"http://{host}:{port}"
    out_dir = Path(cfg.get("output", {}).get("dir") or "out")
    pending = ReviewQueue(out_dir / "review-queue.json").list(status="pending")

    print()
    print("=" * 52)
    print(f"  sub-script app ->  {url}")
    print("=" * 52)
    print("  Opening that URL in your browser...")
    if pending:
        print(f"  Pending clips: {len(pending)}")
    yt = cfg.get("youtube") or {}
    if yt.get("enabled"):
        print("  YouTube upload: ON (Approve will upload Shorts)")
    else:
        print("  YouTube upload: off (Approve saves local pack only)")
        if dry_run_forced():
            print("    (forced off by SUB_SCRIPT_DRY_RUN=1 in .env / environment)")
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        print(f"  ffmpeg: {ffmpeg}")
    else:
        print("  ffmpeg: NOT FOUND — clipping will fail (see FFMPEG_BESIDE_APP.txt)")
    hotkey = cfg.get("hotkey") or "ctrl+shift+c"
    print(f"  Live hotkey: {hotkey} (Start watcher on the home page)")
    print("  Leave this window open while you use the app.")
    print()

    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    uvicorn.run(create_app(cfg), host=host, port=port)


if __name__ == "__main__":
    main()
