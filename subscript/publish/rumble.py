"""Rumble publisher — manual handoff by default; API mode raises NotConfiguredError."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult
from subscript.publish.manual import manual_handoff

_INSTRUCTIONS = """
Rumble — manual post steps
==========================
1. Open https://rumble.com/upload.php (sign in).
2. Upload the video in this folder (horizontal or vertical).
3. Set title / description from your clip title.
4. Publish (or save as draft).

To enable a future live API path:
  platforms.rumble.enabled: true
  platforms.rumble.mode: api
  # Rumble upload API (not wired yet).
""".strip()

_API_HOW = (
    "Rumble API not configured. Set platforms.rumble.mode: manual for a local for_rumble/ pack, or add Rumble API credentials when supported. See README → Platform checklist."
)


class RumblePublisher:
    name = "rumble"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._plat = dict((cfg.get("platforms") or {}).get("rumble") or {})

    @property
    def enabled(self) -> bool:
        return bool(self._plat.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        mode = str(self._plat.get("mode") or "manual").lower().strip()
        if mode == "api":
            raise NotConfiguredError(_API_HOW)
        return manual_handoff(
            platform_key="rumble",
            display_name="Rumble",
            path=path,
            meta=meta,
            instructions=_INSTRUCTIONS,
        )
