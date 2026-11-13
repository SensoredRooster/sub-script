"""Clip performance tracking: learn what works from YouTube stats.

Every approved clip carries its "DNA" (edit preset, brand package, moment
score). When a clip is published to YouTube we record the video id alongside
that DNA. ``refresh_stats`` pulls public view/like counts via the YouTube Data
API (the existing upload authorization can read them — no extra Google
permission needed), and the per-package / per-preset averages feed back into
brand-package auto-selection.

Storage: ``<out_dir>/analytics.json``. Everything is fail-soft — a missing
token or network error just means "no stats yet".
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_STORE = "analytics.json"


def _store_path(out_dir: Path) -> Path:
    return Path(out_dir) / _STORE


def _load(out_dir: Path) -> dict[str, Any]:
    path = _store_path(out_dir)
    if not path.is_file():
        return {"clips": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("clips", {})
        return data
    except Exception:
        return {"clips": {}}


def _save(out_dir: Path, data: dict[str, Any]) -> None:
    path = _store_path(out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def extract_video_id(url: str | None) -> str | None:
    """Pull a YouTube video id out of youtu.be / watch / shorts URLs."""
    if not url:
        return None
    m = re.search(r"youtu\.be/([\w-]{6,})", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]v=([\w-]{6,})", url)
    if m:
        return m.group(1)
    m = re.search(r"youtube\.com/shorts/([\w-]{6,})", url)
    if m:
        return m.group(1)
    return None


def record_publication(
    out_dir: Path,
    *,
    video_id: str,
    item_id: str,
    title: str = "",
    dna: dict[str, Any] | None = None,
) -> None:
    """Link a published YouTube video to the DNA of the clip that made it."""
    if not video_id:
        return
    data = _load(out_dir)
    data["clips"][video_id] = {
        "video_id": video_id,
        "item_id": item_id,
        "title": title,
        "dna": dict(dna or {}),
        "published_at": time.time(),
        "stats": None,
        "stats_fetched_at": None,
    }
    _save(out_dir, data)


def _youtube_credentials(cfg: dict[str, Any]):
    """Reuse the saved YouTube OAuth token, or None if not usable."""
    try:
        from google.oauth2.credentials import Credentials

        from subscript.secure_store import read_token_text
        from subscript.upload import YOUTUBE_UPLOAD_SCOPE, token_path

        youtube = cfg.get("youtube") or {}
        raw = read_token_text(token_path(youtube)) or "{}"
        creds = Credentials.from_authorized_user_info(json.loads(raw), [YOUTUBE_UPLOAD_SCOPE])
        if not (creds.valid or creds.refresh_token):
            return None
        if not creds.valid and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
        return creds
    except Exception:
        return None


def refresh_stats(cfg: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Fetch current view/like counts for every tracked video.

    Returns ``{"updated": n, "clips": total, "error": str|None}``.
    Fail-soft: network/auth problems return an error string, never raise.
    """
    data = _load(out_dir)
    ids = list(data["clips"].keys())
    if not ids:
        return {"updated": 0, "clips": 0, "error": None}

    creds = _youtube_credentials(cfg)
    if creds is None:
        return {"updated": 0, "clips": len(ids),
                "error": "YouTube is not connected — connect it under Publish to track performance."}

    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        updated = 0
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            resp = (
                youtube.videos()
                .list(part="statistics", id=",".join(batch), maxResults=50)
                .execute()
            )
            for entry in resp.get("items", []):
                vid = entry.get("id")
                stats = entry.get("statistics") or {}
                if vid in data["clips"]:
                    data["clips"][vid]["stats"] = {
                        "views": int(stats.get("viewCount", 0) or 0),
                        "likes": int(stats.get("likeCount", 0) or 0),
                        "comments": int(stats.get("commentCount", 0) or 0),
                    }
                    data["clips"][vid]["stats_fetched_at"] = time.time()
                    updated += 1
        _save(out_dir, data)
        return {"updated": updated, "clips": len(ids), "error": None}
    except Exception as exc:  # noqa: BLE001 — analytics must never break the app
        return {"updated": 0, "clips": len(ids), "error": f"Could not fetch stats ({exc})."}


def performance_by(out_dir: Path, key: str) -> dict[str, dict[str, Any]]:
    """Average views grouped by a DNA key (``package_id`` or ``preset``).

    Only clips with fetched stats count. Returns
    ``{value: {"clips": n, "avg_views": float, "avg_likes": float}}``.
    """
    data = _load(out_dir)
    groups: dict[str, list[dict[str, int]]] = {}
    for clip in data["clips"].values():
        stats = clip.get("stats")
        if not stats:
            continue
        group_key = str((clip.get("dna") or {}).get(key) or "unknown")
        groups.setdefault(group_key, []).append(stats)
    out: dict[str, dict[str, Any]] = {}
    for gkey, rows in groups.items():
        out[gkey] = {
            "clips": len(rows),
            "avg_views": sum(r["views"] for r in rows) / len(rows),
            "avg_likes": sum(r["likes"] for r in rows) / len(rows),
        }
    return out


def performance_summary(out_dir: Path) -> str:
    """One plain-language line about what's working, or '' when no data."""
    by_pkg = performance_by(out_dir, "package_id")
    measured = {k: v for k, v in by_pkg.items() if v["clips"] >= 1}
    if not measured:
        return ""
    best = max(measured.items(), key=lambda kv: kv[1]["avg_views"])
    total = sum(v["clips"] for v in measured.values())
    return (
        f"Learning from {total} published clip{'s' if total != 1 else ''}: "
        f"“{best[0]}” clips average {best[1]['avg_views']:.0f} views."
    )
