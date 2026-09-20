"""TikTok publisher — manual handoff by default; API mode raises NotConfiguredError."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult
from subscript.publish.manual import manual_handoff

_INSTRUCTIONS = """
TikTok — manual post steps
==========================
1. Open TikTok (app or https://www.tiktok.com/tiktokstudio/upload ).
2. Upload the video in this folder (prefer vertical_captioned.mp4 / vertical.mp4).
3. Add caption / hashtags from your clip title.
4. Post (or save as draft).

To enable a future live API path:
  platforms.tiktok.enabled: true
  platforms.tiktok.mode: api
  # plus TikTok Content Posting API credentials (not wired yet).
""".strip()

_API_HOW = (
    "TikTok API not configured. Set platforms.tiktok.mode: manual for a local for_tiktok/ pack, or add TikTok Content Posting API credentials when supported. See README → Platform checklist."
)


class TikTokPublisher:
    name = "tiktok"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._plat = dict((cfg.get("platforms") or {}).get("tiktok") or {})

    @property
    def enabled(self) -> bool:
        return bool(self._plat.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        mode = str(self._plat.get("mode") or "manual").lower().strip()
        if mode == "api":
            raise NotConfiguredError(_API_HOW)
        return manual_handoff(
            platform_key="tiktok",
            display_name="TikTok",
            path=path,
            meta=meta,
            instructions=_INSTRUCTIONS,
        )
