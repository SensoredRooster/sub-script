"""Instagram publisher — manual handoff by default; API mode raises NotConfiguredError."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult
from subscript.publish.manual import manual_handoff

_INSTRUCTIONS = """
Instagram Reels — manual post steps
===================================
1. Open Instagram app (Reels) or Meta Business Suite.
2. Create a Reel and upload the vertical video in this folder.
3. Add caption / hashtags from your clip title.
4. Share.

To enable a future live API path:
  platforms.instagram.enabled: true
  platforms.instagram.mode: api
  # Instagram Graph API / Content Publishing (not wired yet).
""".strip()

_API_HOW = (
    "Instagram API not configured. Set platforms.instagram.mode: manual for a local for_instagram/ pack, or add Meta Graph API credentials when supported. See README → Platform checklist."
)


class InstagramPublisher:
    name = "instagram"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._plat = dict((cfg.get("platforms") or {}).get("instagram") or {})

    @property
    def enabled(self) -> bool:
        return bool(self._plat.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        mode = str(self._plat.get("mode") or "manual").lower().strip()
        if mode == "api":
            raise NotConfiguredError(_API_HOW)
        return manual_handoff(
            platform_key="instagram",
            display_name="Instagram",
            path=path,
            meta=meta,
            instructions=_INSTRUCTIONS,
        )
