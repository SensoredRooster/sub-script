"""YouTube Shorts publisher — wraps existing upload.py (only live API by default)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.publish.base import PublishMeta, PublishResult
from subscript.upload import dry_run_upload, upload_youtube


def youtube_live_enabled(cfg: dict[str, Any]) -> bool:
    """Live upload when platforms.youtube.enabled OR legacy youtube.enabled is true."""
    plat = (cfg.get("platforms") or {}).get("youtube") or {}
    yt = cfg.get("youtube") or {}
    return bool(plat.get("enabled") or yt.get("enabled"))


class YouTubePublisher:
    name = "youtube"

    def __init__(self, cfg: dict[str, Any], out_dir: Path) -> None:
        self._cfg = cfg
        self._yt = dict(cfg.get("youtube") or {})
        self._out_dir = Path(out_dir)
        self._yt["enabled"] = youtube_live_enabled(cfg)

    @property
    def enabled(self) -> bool:
        return bool(self._yt.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        path = Path(path)
        if not self.enabled:
            payload = dry_run_upload(path, self._yt, self._out_dir)
            return PublishResult(
                platform="YouTube",
                ok=True,
                status="dry_run",
                message="youtube.enabled=false",
                detail=payload,
            )
        try:
            result = upload_youtube(path, self._yt)
        except Exception as exc:  # noqa: BLE001
            return PublishResult(
                platform="YouTube",
                ok=False,
                status="error",
                message=str(exc),
            )
        url = result.get("url") or result.get("shorts_url")
        return PublishResult(
            platform="YouTube",
            ok=True,
            status="uploaded",
            message=result.get("title") or "uploaded",
            url=url,
            detail=result,
        )
