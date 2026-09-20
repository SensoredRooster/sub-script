"""Orchestrate clip → brand → upload."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from subscript.brand import apply_brand
from subscript.buffer import BufferSource
from subscript.clip import clip_last_seconds
from subscript.upload import dry_run_upload, upload_youtube


def run_pipeline(
    source: Path,
    cfg: dict[str, Any],
    *,
    dry_run: bool = True,
) -> Path:
    seconds = int(cfg.get("buffer_seconds") or 30)
    out_dir = Path(cfg.get("output", {}).get("dir") or "out")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = out_dir / f"clip-raw-{stamp}.mp4"
    branded = out_dir / f"clip-branded-{stamp}.mp4"

    src = BufferSource(path=source, buffer_seconds=seconds).resolve()
    clip_last_seconds(src, raw, seconds=seconds)
    apply_brand(raw, branded, cfg.get("brand") or {})

    yt = cfg.get("youtube") or {}
    if dry_run or not yt.get("enabled"):
        dry_run_upload(branded, yt, out_dir)
        print(f"Dry-run complete: {branded}")
    else:
        upload_youtube(branded, yt)
        print(f"Uploaded: {branded}")
    return branded
