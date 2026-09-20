"""Facebook publisher — manual handoff by default; API mode raises NotConfiguredError."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult
from subscript.publish.manual import manual_handoff

_INSTRUCTIONS = """
Facebook — manual post steps
============================
1. Open Facebook (app or https://www.facebook.com/ ).
2. Create a Reel or upload video; use the file in this folder.
3. Add description from your clip title.
4. Post to your Page or profile.

To enable a future live API path:
  platforms.facebook.enabled: true
  platforms.facebook.mode: api
  # Meta Graph API Page publishing (not wired yet).
""".strip()

_API_HOW = (
    "Facebook API not configured. Set platforms.facebook.mode: manual for a local for_facebook/ pack, or add Meta Page access tokens when supported. See README → Platform checklist."
)


class FacebookPublisher:
    name = "facebook"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._plat = dict((cfg.get("platforms") or {}).get("facebook") or {})

    @property
    def enabled(self) -> bool:
        return bool(self._plat.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        mode = str(self._plat.get("mode") or "manual").lower().strip()
        if mode == "api":
            raise NotConfiguredError(_API_HOW)
        return manual_handoff(
            platform_key="facebook",
            display_name="Facebook",
            path=path,
            meta=meta,
            instructions=_INSTRUCTIONS,
        )
