"""Orchestrate clip -> brand -> horizontal/vertical -> music -> captions -> review queue."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from subscript.brand import apply_brand
from subscript.buffer import BufferSource
from subscript.captions import maybe_caption_vertical
from subscript.clip import clip_last_seconds
from subscript.music import maybe_mix_social_pair
from subscript.queue import ReviewQueue
from subscript.reframe import make_social_pair


def run_pipeline(
    source: Path,
    cfg: dict[str, Any],
    *,
    dry_run: bool = True,
    start: float | None = None,
    duration: float | None = None,
) -> Path:
    default_seconds = int(cfg.get("buffer_seconds") or 30)
    seconds = int(duration) if duration is not None else default_seconds
    out_cfg = cfg.get("output") or {}
    out_dir = Path(out_cfg.get("dir") or "out")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = out_dir / f"clip-raw-{stamp}.mp4"
    branded = out_dir / f"clip-branded-{stamp}.mp4"

    src = BufferSource(path=source, buffer_seconds=seconds).resolve()
    clip_last_seconds(src, raw, seconds=seconds, start=start)
    apply_brand(raw, branded, cfg.get("brand") or {})

    shorts_w = int(out_cfg.get("shorts_width") or 1080)
    shorts_h = int(out_cfg.get("shorts_height") or 1920)
    land_w = int(out_cfg.get("landscape_width") or 1920)
    land_h = int(out_cfg.get("landscape_height") or 1080)
    horizontal, vertical = make_social_pair(
        branded,
        out_dir,
        stamp,
        shorts_w=shorts_w,
        shorts_h=shorts_h,
        landscape_w=land_w,
        landscape_h=land_h,
    )

    # Optional music bed under both social exports (skip if missing / disabled).
    horizontal, vertical = maybe_mix_social_pair(
        horizontal, vertical, out_dir, stamp, cfg
    )

    # Captions after H+V (+ music): whisper when available, else demo SRT.
    captioned = maybe_caption_vertical(
        vertical, out_dir, stamp, cfg, duration_s=float(seconds)
    )

    require_approval = bool((cfg.get("review") or {}).get("require_approval", True))
    if require_approval:
        queue = ReviewQueue(out_dir / "review-queue.json")
        item = queue.enqueue(
            branded,
            src,
            title=f"Highlight {stamp}",
            horizontal_path=horizontal,
            vertical_path=vertical,
            vertical_captioned_path=captioned,
        )
        host = (cfg.get("review") or {}).get("host", "127.0.0.1")
        port = int((cfg.get("review") or {}).get("port", 8787))
        print(f"Queued for review ({item.id})")
        print(f"  master:      {branded}")
        print(f"  horizontal: {horizontal}")
        print(f"  vertical:   {vertical}")
        if captioned:
            print(f"  captioned:  {captioned}")
        print(f"Open the app: run-app.bat  ->  http://{host}:{port}")
        return branded

    from subscript.upload import dry_run_upload, upload_youtube

    yt = cfg.get("youtube") or {}
    upload_target = captioned or vertical
    if dry_run or not yt.get("enabled"):
        dry_run_upload(upload_target, yt, out_dir)
        print(f"Dry-run complete: {upload_target}")
    else:
        upload_youtube(upload_target, yt)
        print(f"Uploaded: {upload_target}")
    return branded
