"""X publisher — manual handoff by default; API mode raises NotConfiguredError."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult
from subscript.publish.manual import manual_handoff

_INSTRUCTIONS = """
X (Twitter) — manual post steps
===============================
1. Open https://x.com/compose/post (or the X app).
2. Attach the video in this folder (vertical works; keep under X size/duration limits).
3. Write the post text from your clip title.
4. Post.

To enable a future live API path:
  platforms.twitter.enabled: true
  platforms.twitter.mode: api
  # X API v2 media upload (not wired yet).
""".strip()

_API_HOW = (
    "X/Twitter API not configured. Set platforms.twitter.mode: manual for a local for_twitter/ pack, or add X API keys when supported. See README → Platform checklist."
)


class TwitterPublisher:
    name = "twitter"

    def __init__(self, cfg: dict[str, Any]) -> None:
        platforms = cfg.get("platforms") or {}
        self._plat = dict(platforms.get("twitter") or platforms.get("x") or {})

    @property
    def enabled(self) -> bool:
        return bool(self._plat.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        mode = str(self._plat.get("mode") or "manual").lower().strip()
        if mode == "api":
            raise NotConfiguredError(_API_HOW)
        return manual_handoff(
            platform_key="twitter",
            display_name="X",
            path=path,
            meta=meta,
            instructions=_INSTRUCTIONS,
        )
