"""Approve fan-out: call every enabled publisher, fail-soft per platform."""

from __future__ import annotations

from pathlib import Path
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
    for pub in build_publishers(cfg, out_dir):
        if not pub.enabled:
            continue
        try:
            results.append(pub.publish(path, meta))
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
