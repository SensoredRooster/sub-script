"""Local app UI: drop a VOD -> clip -> approve / trim / reject."""

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
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from subscript.branding_routes import branding_html, register_branding_routes
from subscript.captions import maybe_caption_vertical
from subscript.config import load_config
from subscript.pipeline import run_pipeline
from subscript.publish import publish_local
from subscript.queue import ReviewQueue
from subscript.reframe import make_social_pair
from subscript.trim import trim_clip
from subscript.upload import dry_run_upload, upload_youtube

_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_STATIC = Path(__file__).resolve().parent / "static"
_SNIPPETS = _STATIC / "snippets"


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

    app = FastAPI(title="sub-script")
    _STATIC.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    register_branding_routes(app, cfg)

    @app.get("/", response_class=HTMLResponse)
    def home(msg: str | None = None, err: str | None = None) -> str:
        pending = queue.list(status="pending")
        rows = []
        card_tpl = _snip("card.html")
        for item in pending:
            rows.append(
                card_tpl.replace("{{ID}}", _esc(item.id))
                .replace("{{TITLE}}", _esc(item.title))
                .replace("{{CREATED}}", _esc(item.created_at))
            )
        review = "\n".join(rows) or _snip("empty.html")
        banner = ""
        if err:
            banner = f'<p class="banner bad-banner">{_esc(err)}</p>'
        elif msg:
            banner = f'<p class="banner ok-banner">{_esc(msg)}</p>'
        form = _snip("clip_form.html").replace("{{DEFAULT_SECONDS}}", str(default_seconds))
        branding = branding_html(cfg.get("brand") or {}, _snip)
        body = form + branding + banner + f'<section id="review">{review}</section>'
        return _snip("page.html").replace("{{BODY}}", body)

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
            if mode == "last30":
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
                source, cfg, dry_run=True, start=clip_start, duration=clip_duration
            )
        except Exception as exc:  # noqa: BLE001
            return RedirectResponse(f"/?err={quote(str(exc), safe='')}", status_code=303)
        return RedirectResponse(
            "/?msg="
            + quote(
                "Ready - horizontal + vertical (+ captioned) previews below. "
                "Approve saves a social pack to out\\approved\\.",
                safe="",
            ),
            status_code=303,
        )

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

    @app.post("/items/{item_id}/approve")
    def approve(item_id: str) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        meta = publish_local(
            item_id=item_id,
            title=item.title,
            out_dir=out_dir,
            master=Path(item.edited_path or item.video_path),
            horizontal=Path(item.horizontal_path) if item.horizontal_path else None,
            vertical=Path(item.vertical_path) if item.vertical_path else None,
            vertical_captioned=(
                Path(item.vertical_captioned_path)
                if item.vertical_captioned_path
                else None
            ),
        )
        upload_src = Path(
            item.vertical_captioned_path
            or item.vertical_path
            or item.edited_path
            or item.video_path
        )
        _do_upload(upload_src, cfg, out_dir)
        queue.set_status(item_id, "approved")
        folder = str(out_dir / "approved" / item_id)
        n = len(meta.get("files") or [])
        return RedirectResponse(
            "/?msg="
            + quote(
                f"Approved - social pack ({n} file(s)) saved to {folder} (folder opened).",
                safe="",
            ),
            status_code=303,
        )

    @app.post("/items/{item_id}/trim")
    def trim_and_approve(
        item_id: str, start: float = Form(...), end: float = Form(...)
    ) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        dest = out_dir / f"clip-trimmed-{item_id}.mp4"
        trim_clip(Path(item.video_path), dest, start=start, end=end)
        out_cfg = cfg.get("output") or {}
        stamp = item_id
        horizontal, vertical = make_social_pair(
            dest,
            out_dir,
            stamp,
            shorts_w=int(out_cfg.get("shorts_width") or 1080),
            shorts_h=int(out_cfg.get("shorts_height") or 1920),
            landscape_w=int(out_cfg.get("landscape_width") or 1920),
            landscape_h=int(out_cfg.get("landscape_height") or 1080),
        )
        dur = max(0.1, float(end) - float(start))
        captioned = maybe_caption_vertical(
            vertical, out_dir, stamp, cfg, duration_s=dur
        )
        queue.set_status(
            item_id,
            "pending",
            trim_start=start,
            trim_end=end,
            edited_path=str(dest),
            video_path=str(dest),
            horizontal_path=str(horizontal),
            vertical_path=str(vertical),
            vertical_captioned_path=str(captioned) if captioned else None,
        )
        return RedirectResponse(
            "/?msg="
            + quote(
                "Trimmed - new horizontal + vertical (+ captioned) previews ready. "
                "Approve when happy.",
                safe="",
            ),
            status_code=303,
        )

    @app.post("/items/{item_id}/reject")
    def reject(item_id: str) -> RedirectResponse:
        if not queue.get(item_id):
            raise HTTPException(404)
        queue.set_status(item_id, "rejected")
        return RedirectResponse("/?msg=" + quote("Rejected.", safe=""), status_code=303)

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


def _do_upload(video: Path, cfg: dict[str, Any], out_dir: Path) -> None:
    yt = cfg.get("youtube") or {}
    if yt.get("enabled"):
        upload_youtube(video, yt)
    else:
        dry_run_upload(video, yt, out_dir)


def _esc(value: str) -> str:
    return (
        value.replace("&", "&")
        .replace("<", "<")
        .replace(">", ">")
        .replace('"', """)
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
    print("  Leave this window open while you use the app.")
    print()

    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass

    uvicorn.run(create_app(cfg), host=host, port=port)


if __name__ == "__main__":
    main()
