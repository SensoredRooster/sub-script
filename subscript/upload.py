"""YouTube Shorts upload + dry-run mock."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def dry_run_upload(video: Path, youtube_cfg: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Record what would be uploaded without calling YouTube."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = (youtube_cfg.get("title_template") or "Highlight {timestamp}").format(
        timestamp=stamp
    )
    payload = {
        "dry_run": True,
        "file": str(video),
        "title": title,
        "description": youtube_cfg.get("description"),
        "privacy": youtube_cfg.get("privacy", "private"),
        "tags": youtube_cfg.get("tags") or [],
        "category_id": youtube_cfg.get("category_id", "20"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = out_dir / f"upload-dry-run-{stamp}.json"
    meta.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def upload_youtube(video: Path, youtube_cfg: dict[str, Any]) -> dict[str, Any]:
    """Stub: wire Google OAuth + videos.insert here.

    Keep credentials in credentials.json / token.json (gitignored).
    """
    if not youtube_cfg.get("enabled"):
        raise RuntimeError("youtube.enabled is false — use --dry-run or enable in config")
    raise NotImplementedError(
        "YouTube upload stub — add OAuth + videos.insert when credentials are ready"
    )
