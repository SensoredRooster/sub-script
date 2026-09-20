"""Approve fan-out: call every enabled publisher, fail-soft per platform."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import json
from typing import Any

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult, Publisher
from subscript.publish.facebook import FacebookPublisher
from subscript.publish.instagram import InstagramPublisher
from subscript.publish.rumble import RumblePublisher
from subscript.publish.tiktok import TikTokPublisher
from subscript.publish.twitter import TwitterPublisher
from subscript.publish.youtube import YouTubePublisher


def build_publishers(cfg: dict[str, Any], out_dir: Path) -> list[Publisher]:
    """All platform publishers (caller filters on ``.enabled``)."""
    return [
        YouTubePublisher(cfg, out_dir),
        TikTokPublisher(cfg),
        InstagramPublisher(cfg),
        FacebookPublisher(cfg),
        TwitterPublisher(cfg),
        RumblePublisher(cfg),
    ]


def run_enabled_publishers(
    path: Path,
    meta: PublishMeta,
    cfg: dict[str, Any],
    out_dir: Path,
) -> list[PublishResult]:
    """Publish to every enabled platform. Never raises — one failure cannot abort Approve."""
    results: list[PublishResult] = []
    drafts = meta.extra.get("post_metadata") or {}
    if drafts:
        meta.approved_dir.mkdir(parents=True, exist_ok=True)
        (meta.approved_dir / "post-copy.json").write_text(json.dumps(drafts, indent=2, ensure_ascii=False), encoding="utf-8")
    for pub in build_publishers(cfg, out_dir):
        if not pub.enabled:
            continue
        try:
            draft = drafts.get(pub.name)
            platform_meta = replace(meta, title=draft["title"], description=draft["description"], tags=draft["tags"], extra={**meta.extra, "generated_copy": True}) if draft else meta
            results.append(pub.publish(path, platform_meta))
        except NotConfiguredError as exc:
            results.append(
                PublishResult(
                    platform=getattr(pub, "name", "platform").title(),
                    ok=False,
                    status="not_configured",
                    message=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                PublishResult(
                    platform=getattr(pub, "name", "platform").title(),
                    ok=False,
                    status="error",
                    message=str(exc),
                )
            )
    return results


def format_platform_banner(results: list[PublishResult]) -> str:
    """Single-line / multi-clause status for the UI banner."""
    if not results:
        return "No platforms enabled (flip flags under config platforms:)."
    return " | ".join(r.banner_line() for r in results)
