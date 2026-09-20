"""Approve / trim / reject routes for the review app."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Form, HTTPException
from fastapi.responses import RedirectResponse

from subscript.captions import maybe_caption_vertical
from subscript.publish import publish_local
from subscript.reframe import make_social_pair
from subscript.trim import trim_clip
from subscript.upload import dry_run_upload, upload_youtube


def _do_upload(video: Path, cfg: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    yt = cfg.get("youtube") or {}
    if yt.get("enabled"):
        return upload_youtube(video, yt)
    return dry_run_upload(video, yt, out_dir)


def register_item_routes(app, cfg: dict[str, Any], queue, out_dir: Path) -> None:
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
        folder = str(out_dir / "approved" / item_id)
        n = len(meta.get("files") or [])
        try:
            result = _do_upload(upload_src, cfg, out_dir)
        except Exception as exc:  # noqa: BLE001
            queue.set_status(item_id, "approved")
            return RedirectResponse(
                "/?err="
                + quote(
                    f"Saved pack to {folder} (folder opened), "
                    f"but YouTube upload failed: {exc}",
                    safe="",
                ),
                status_code=303,
            )

        if result.get("dry_run"):
            queue.set_status(item_id, "approved")
            msg = (
                f"Approved - social pack ({n} file(s)) saved to {folder} "
                f"(folder opened). YouTube skipped (youtube.enabled=false)."
            )
        else:
            queue.set_status(item_id, "uploaded")
            url = result.get("url") or result.get("shorts_url") or ""
            msg = (
                f"Approved - uploaded to YouTube: {url} — "
                f"also saved pack ({n} file(s)) to {folder} (folder opened)."
            )
        return RedirectResponse("/?msg=" + quote(msg, safe=""), status_code=303)

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
