"""Approve / trim / reject routes for the review app."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Form, HTTPException
from fastapi.responses import RedirectResponse

from subscript.captions import maybe_caption_vertical
from subscript.publish import (
    PublishMeta,
    format_platform_banner,
    publish_local,
    run_enabled_publishers,
)
from subscript.publish.youtube import youtube_live_enabled
from subscript.reframe import make_social_pair
from subscript.trim import trim_clip


def register_item_routes(app, cfg: dict[str, Any], queue, out_dir: Path) -> None:
    @app.post("/items/{item_id}/approve")
    def approve(item_id: str) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)

        # 1) Always build the shared local social pack (opens folder).
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
        approved_dir = out_dir / "approved" / item_id
        folder = str(approved_dir)
        n = len(meta.get("files") or [])

        # 2) Fan out to every enabled platform — fail-soft per platform.
        publish_meta = PublishMeta(
            item_id=item_id,
            title=item.title,
            out_dir=out_dir,
            approved_dir=approved_dir,
            description=(cfg.get("youtube") or {}).get("description") or "",
            tags=list((cfg.get("youtube") or {}).get("tags") or []),
        )
        results = run_enabled_publishers(upload_src, publish_meta, cfg, out_dir)
        platform_banner = format_platform_banner(results)
        if not youtube_live_enabled(cfg) and not any(
            (r.platform or "").lower().startswith("youtube") for r in results
        ):
            platform_banner = (
                "YouTube: skipped (disabled) | " + platform_banner
                if results
                else "YouTube: skipped (disabled) — enable platforms.* or youtube.enabled"
            )

        any_upload = any(r.ok and r.status == "uploaded" for r in results)
        any_hard_fail = any(not r.ok for r in results)
        queue.set_status(item_id, "uploaded" if any_upload else "approved")

        msg = (
            f"Approved — social pack ({n} file(s)) saved to {folder} "
            f"(folder opened). {platform_banner}"
        )
        # Pack always succeeds; platform failures stay in the banner (fail-soft).
        if any_hard_fail and not any_upload:
            return RedirectResponse(
                "/?err=" + quote(msg, safe=""),
                status_code=303,
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
