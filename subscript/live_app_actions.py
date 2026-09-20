"""Approve / trim / reject routes for the review app."""

from __future__ import annotations

from datetime import datetime, timezone
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
from subscript.post_metadata import PLATFORMS, generate_posts


def _redirect_err(message: str) -> RedirectResponse:
    return RedirectResponse("/?err=" + quote(message, safe=""), status_code=303)


def _redirect_ok(message: str) -> RedirectResponse:
    return RedirectResponse("/?msg=" + quote(message, safe=""), status_code=303)


def register_item_routes(app, cfg: dict[str, Any], queue, out_dir: Path) -> None:
    @app.post("/items/{item_id}/post-copy")
    def save_post_copy(item_id: str, platform: str = Form(...), title: str = Form(...),
                       description: str = Form(""), tags: str = Form("")):
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        if item.status != "pending":
            return _redirect_err("Only pending clips can be edited.")
        if platform not in PLATFORMS or not title.strip() or len(title) > 95 or len(description) > (260 if platform == "twitter" else 1800):
            return _redirect_err("Check the platform, title, and description lengths.")
        parsed_tags = list(dict.fromkeys(t.strip().lstrip("#") for t in tags.split(",") if t.strip().lstrip("#")))
        if len(parsed_tags) > 15 or sum(len(t) for t in parsed_tags) > 350:
            return _redirect_err("Use at most 15 tags and 350 tag characters.")
        item.post_metadata[platform] = {"title": title.strip(), "description": description.strip(), "tags": parsed_tags, "basis": "Edited by you"}
        queue.update(item)
        return RedirectResponse("/?msg=Post%20draft%20saved.#review", status_code=303)

    @app.post("/items/{item_id}/approve")
    def approve(item_id: str) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        if item.status != "pending":
            return _redirect_err(f"Clip {item_id} is already {item.status}.")

        # 1) Always build the shared local social pack (opens folder).
        try:
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
        except Exception as exc:  # noqa: BLE001 — keep the item pending, show why
            return _redirect_err(f"Approve failed while building the social pack: {exc}")

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
            extra={"post_metadata": item.post_metadata},
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
            return _redirect_err(msg)
        return _redirect_ok(msg)

    @app.post("/items/{item_id}/trim")
    def trim_and_approve(
        item_id: str, start: float = Form(...), end: float = Form(...)
    ) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        if item.status != "pending":
            return _redirect_err(f"Clip {item_id} is already {item.status}.")
        try:
            start_s = float(start)
            end_s = float(end)
            if start_s < 0:
                raise ValueError("Start must be 0 or greater.")
            if end_s <= start_s:
                raise ValueError("End must be greater than start.")

            # Always trim from the original branded master so repeated trims do not
            # compound (and never read + overwrite the same file in one ffmpeg run).
            master = Path(item.video_path)
            if not master.is_file():
                raise FileNotFoundError(f"Master clip missing: {master}")
            stamp = f"{item_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            dest = out_dir / f"clip-trimmed-{stamp}.mp4"
            trim_clip(master, dest, start=start_s, end=end_s)

            out_cfg = cfg.get("output") or {}
            horizontal, vertical = make_social_pair(
                dest,
                out_dir,
                stamp,
                shorts_w=int(out_cfg.get("shorts_width") or 1080),
                shorts_h=int(out_cfg.get("shorts_height") or 1920),
                landscape_w=int(out_cfg.get("landscape_width") or 1920),
                landscape_h=int(out_cfg.get("landscape_height") or 1080),
            )
            dur = max(0.1, end_s - start_s)
            captioned = maybe_caption_vertical(
                vertical, out_dir, stamp, cfg, duration_s=dur
            )
        except Exception as exc:  # noqa: BLE001 — show the reason instead of a 500 page
            return _redirect_err(f"Trim failed: {exc}")

        queue.set_status(
            item_id,
            "pending",
            trim_start=start_s,
            trim_end=end_s,
            edited_path=str(dest),
            horizontal_path=str(horizontal),
            vertical_path=str(vertical),
            vertical_captioned_path=str(captioned) if captioned else None,
            post_metadata=generate_posts(cfg, out_dir / f"clip-captions-{stamp}.srt"),
        )
        return _redirect_ok(
            "Trimmed - new horizontal + vertical (+ captioned) previews ready. "
            "Approve when happy."
        )

    @app.post("/items/{item_id}/reject")
    def reject(item_id: str) -> RedirectResponse:
        item = queue.get(item_id)
        if not item:
            raise HTTPException(404)
        if item.status != "pending":
            return _redirect_err(f"Clip {item_id} is already {item.status}.")
        queue.set_status(item_id, "rejected")
        return _redirect_ok("Rejected.")
