"""Local review UI: approve as-is, quick trim, or reject before upload."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from subscript.config import load_config
from subscript.queue import ReviewQueue
from subscript.trim import trim_clip
from subscript.upload import dry_run_upload, upload_youtube


def create_app(cfg: dict[str, Any] | None = None) -> FastAPI:
    cfg = cfg or load_config()
    out_dir = Path(cfg.get("output", {}).get("dir") or "out")
    queue = ReviewQueue(out_dir / "review-queue.json")

    app = FastAPI(title="sub-script review")
    static = Path(__file__).resolve().parent / "static"
    static.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        pending = queue.list(status="pending")
        rows = []
        for item in pending:
            rows.append(
                f"""
                <article class=\"card\" id=\"{item.id}\">
                  <h2>{_esc(item.title)}</h2>
                  <p class=\"meta\">{_esc(item.created_at)} \u00b7 {_esc(item.id)}</p>
                  <video controls src=\"/media/{item.id}\"></video>
                  <form class=\"actions\" method=\"post\" action=\"/items/{item.id}/approve\">
                    <button type=\"submit\" class=\"ok\">Approve as-is</button>
                  </form>
                  <form class=\"actions\" method=\"post\" action=\"/items/{item.id}/trim\">
                    <label>Start (s) <input name=\"start\" type=\"number\" step=\"0.1\" min=\"0\" value=\"0\" required></label>
                    <label>End (s) <input name=\"end\" type=\"number\" step=\"0.1\" min=\"0.1\" value=\"30\" required></label>
                    <button type=\"submit\">Trim &amp; approve</button>
                  </form>
                  <form class=\"actions\" method=\"post\" action=\"/items/{item.id}/reject\">
                    <button type=\"submit\" class=\"bad\">Reject</button>
                  </form>
                </article>
                """
            )
        body = "\n".join(rows) or _empty_state()
        return _page(body)

    @app.get("/media/{item_id}")
    def media(item_id: str) -> FileResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
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
        video = Path(item.edited_path or item.video_path)
        _do_upload(video, cfg, out_dir)
        queue.set_status(item_id, "approved")
        return RedirectResponse("/", status_code=303)

    @app.post("/items/{item_id}/trim")
    def trim_and_approve(
        item_id: str,
        start: float = Form(...),
        end: float = Form(...),
    ) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        dest = out_dir / f"clip-trimmed-{item_id}.mp4"
        trim_clip(Path(item.video_path), dest, start=start, end=end)
        queue.set_status(
            item_id,
            "approved",
            trim_start=start,
            trim_end=end,
            edited_path=str(dest),
        )
        _do_upload(dest, cfg, out_dir)
        return RedirectResponse("/", status_code=303)

    @app.post("/items/{item_id}/reject")
    def reject(item_id: str) -> RedirectResponse:
        if not queue.get(item_id):
            raise HTTPException(404)
        queue.set_status(item_id, "rejected")
        return RedirectResponse("/", status_code=303)

    return app


def _empty_state() -> str:
    return (
        '<section class="empty card">'
        "<h2>No pending clips</h2>"
        "<p>The review queue is empty. Enqueue a branded clip, then refresh this page.</p>"
        "<ol class=\"empty-help\">"
        "<li>In a terminal (venv active):"
        " <code>python -m subscript --source test-clips/your.mp4</code></li>"
        "<li>Refresh this page (F5) to see Approve / Trim &amp; approve / Reject.</li>"
        "</ol>"
        "<p class=\"meta\">Put VODs in <code>test-clips/</code> locally "
        "\u2014 they stay on your machine, not on GitHub.</p>"
        "</section>"
    )


def _do_upload(video: Path, cfg: dict[str, Any], out_dir: Path) -> None:
    yt = cfg.get("youtube") or {}
    if yt.get("enabled"):
        upload_youtube(video, yt)
    else:
        dry_run_upload(video, yt, out_dir)


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _page(body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "  <title>sub-script review</title>\n"
        "  <link rel=\"stylesheet\" href=\"/static/review.css\">\n"
        "</head>\n<body>\n  <header>\n    <h1>sub-script</h1>\n"
        "    <p>Auto-made clips wait here. Approve as-is, quick trim, or reject"
        " \u2014 nothing uploads without you.</p>\n  </header>\n"
        f"  <main>{body}</main>\n</body>\n</html>"
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
    print(f"  Review UI \u2192  {url}")
    print("=" * 52)
    print("  Open that URL in your browser.")
    if not pending:
        print("  Queue is empty. Enqueue a clip first:")
        print("    python -m subscript --source test-clips\\your.mp4")
        print("  Then refresh the page.")
    else:
        print(f"  Pending clips: {len(pending)}")
    print()

    uvicorn.run(create_app(cfg), host=host, port=port)


if __name__ == "__main__":
    main()
