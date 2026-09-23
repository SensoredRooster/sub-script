"""Orchestrate clip -> brand -> horizontal/vertical -> music -> captions -> review queue."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any

from subscript.brand import apply_brand, choose_sequence_assets, compose_brand_sequence
from subscript.buffer import BufferSource
from subscript.captions import maybe_caption_vertical, maybe_caption_horizontal
from subscript.clip import clip_last_seconds
from subscript.music import maybe_mix_social_pair
from subscript.queue import ReviewQueue
from subscript.post_metadata import generate_posts
from subscript.reframe import make_social_pair
from subscript.layout import normalize_layout, probe_media
from subscript.telemetry import log_event


def run_pipeline(
    source: Path,
    cfg: dict[str, Any],
    *,
    dry_run: bool = True,
    start: float | None = None,
    duration: float | None = None,
) -> Path:
    default_seconds = int(cfg.get("buffer_seconds") or 30)
    seconds = (
        max(1, int(round(float(duration)))) if duration is not None else default_seconds
    )
    out_cfg = cfg.get("output") or {}
    out_dir = Path(out_cfg.get("dir") or "out")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw = out_dir / f"clip-raw-{stamp}.mp4"
    branded = out_dir / f"clip-branded-{stamp}.mp4"

    src = BufferSource(path=source, buffer_seconds=seconds).resolve()
    log_event(
        "pipeline_start",
        "Clip pipeline started",
        source_name=src.name,
        start=start,
        duration=duration,
        dry_run=dry_run,
        require_approval=bool((cfg.get("review") or {}).get("require_approval", True)),
    )
    metadata = probe_media(src)
    if metadata and (int(metadata.get("width") or 0) < 2 or int(metadata.get("height") or 0) < 2):
        raise ValueError("The selected recording has no readable video stream. Wait for the recorder to finish writing, then choose it again.")
    if metadata.get("duration") and start is not None and float(start) >= float(metadata["duration"]):
        raise ValueError(f"The clip start ({float(start):g}s) is past this recording's {float(metadata['duration']):g}s duration.")
    clip_last_seconds(src, raw, seconds=seconds, start=start)
    brand_cfg = cfg.get("brand") or {}
    intro, outro = choose_sequence_assets(brand_cfg, stamp)
    if intro or outro:
        branded_core = out_dir / f"clip-branded-core-{stamp}.mp4"
        apply_brand(raw, branded_core, brand_cfg)
        parts = [path for path in (intro, branded_core, outro) if path is not None]
        try:
            compose_brand_sequence(
                parts,
                branded,
                width=int(out_cfg.get("landscape_width") or 1920),
                height=int(out_cfg.get("landscape_height") or 1080),
            )
        except Exception as exc:  # noqa: BLE001 — a bad optional bumper never blocks clipping
            print(f"Brand sequence skipped ({exc}); continuing with the gameplay clip.")
            shutil.copy2(branded_core, branded)
        finally:
            branded_core.unlink(missing_ok=True)
    else:
        apply_brand(raw, branded, brand_cfg)

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
        vertical_layout=normalize_layout(cfg.get("vertical_layout")),
    )

    # Optional music bed under both social exports (skip if missing / disabled).
    horizontal, vertical = maybe_mix_social_pair(
        horizontal, vertical, out_dir, stamp, cfg
    )

    # Captions after H+V (+ music): whisper when available, else demo SRT.
    captioned = maybe_caption_vertical(
        vertical, out_dir, stamp, cfg, duration_s=float(seconds)
    )
    horizontal = maybe_caption_horizontal(horizontal, out_dir, stamp, cfg)

    require_approval = bool((cfg.get("review") or {}).get("require_approval", True))
    posts = generate_posts(cfg, out_dir / f"clip-captions-{stamp}.srt")
    if require_approval:
        queue = ReviewQueue(out_dir / "review-queue.json")
        item = queue.enqueue(
            branded,
            src,
            title=f"Highlight {stamp}",
            horizontal_path=horizontal,
            vertical_path=vertical,
            vertical_captioned_path=captioned,
            post_metadata=posts,
            vertical_layout=normalize_layout(cfg.get("vertical_layout")),
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
        log_event("pipeline_review_ready", "Clip queued for review", item_id=item.id, source_name=src.name)
        return branded

    if dry_run:
        from subscript.upload import dry_run_upload
        dry_run_upload(captioned or vertical, cfg.get("youtube") or {}, out_dir)
        log_event("pipeline_dry_run_complete", "Dry-run pipeline completed", source_name=src.name)
        return branded

    # Persist a review item first so interrupted or failed delivery retains the clip.
    import json
    from copy import deepcopy
    from dataclasses import asdict
    from subscript.config import apply_env_overrides
    from subscript.publish import PublishMeta, publish_local, run_enabled_publishers, format_platform_banner

    queue = ReviewQueue(out_dir / "review-queue.json")
    item = queue.enqueue(branded, src, title=f"Highlight {stamp}",
                         horizontal_path=horizontal, vertical_path=vertical,
                         vertical_captioned_path=captioned,
                         vertical_layout=normalize_layout(cfg.get("vertical_layout")),
                         post_metadata=posts)
    publish_local(item_id=item.id, title=item.title, out_dir=out_dir,
                  master=branded, horizontal=horizontal, vertical=vertical,
                  vertical_captioned=captioned, open_folder=False)
    approved_dir = out_dir / "approved" / item.id
    yt = cfg.get("youtube") or {}
    meta = PublishMeta(item_id=item.id, title=item.title, out_dir=out_dir,
                       approved_dir=approved_dir, description=yt.get("description") or "",
                       tags=list(yt.get("tags") or []), extra={"post_metadata": posts})
    results = run_enabled_publishers(
        captioned or vertical, meta, apply_env_overrides(deepcopy(cfg)), out_dir
    )
    (approved_dir / "publishing-results.json").write_text(
        json.dumps([asdict(result) for result in results], indent=2), encoding="utf-8")
    uploaded = any(result.ok and result.status == "uploaded" for result in results)
    failed = any(not result.ok for result in results)
    # Do not expose an already-uploaded clip to a one-click retry of every destination.
    queue.set_status(item.id, "uploaded" if uploaded else "pending" if failed else "approved")
    if failed:
        log_event("pipeline_publish_failed", "Automatic publishing needs attention", level=40, item_id=item.id)
        raise RuntimeError("Automatic publishing needs attention. Export pack saved. " + format_platform_banner(results))
    print(format_platform_banner(results))
    log_event("pipeline_complete", "Automatic pipeline completed", item_id=item.id, uploaded=uploaded, source_name=src.name)
    return branded
