"""Rolling capture buffer / live source resolver.

v1: treat a finished recording (or OBS replay buffer export) as the source
file. Also supports a watch folder — pick the newest video by mtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".ts"}


@dataclass
class BufferSource:
    path: Path
    buffer_seconds: int = 30

    def resolve(self) -> Path:
        if not self.path.exists():
            raise FileNotFoundError(f"Source video not found: {self.path}")
        if self.path.is_dir():
            newest = newest_video_in(self.path)
            if newest is None:
                raise FileNotFoundError(
                    f"No video files found in watch folder: {self.path}"
                )
            return newest
        return self.path


def newest_video_in(folder: Path) -> Path | None:
    """Return the most recently modified video under `folder` (non-recursive)."""
    if not folder.is_dir():
        return None
    candidates: list[Path] = []
    for p in folder.iterdir():
        if not p.is_file() or p.suffix.lower() not in _VIDEO_SUFFIXES:
            continue
        # Recorders often leave a zero-byte or still-locked file briefly.  Do not
        # select obvious partial exports or files that cannot be opened yet.
        if p.name.lower().endswith((".tmp", ".part", ".partial")) or p.stat().st_size <= 0:
            continue
        try:
            with p.open("rb") as handle:
                handle.read(1)
        except OSError:
            continue
        candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_live_source(cfg: dict[str, Any], override: Path | None = None) -> Path:
    """Pick the rolling source for a live hotkey fire.

    Order:
      1. Explicit override path (CLI --source)
      2. config live_source (OBS replay export file or folder)
      3. config watch_folder (newest video by mtime)
    """
    if override is not None:
        return BufferSource(path=override).resolve()

    live_source = (cfg.get("live_source") or "").strip()
    if live_source:
        return BufferSource(path=Path(live_source)).resolve()

    watch_folder = (cfg.get("watch_folder") or "").strip()
    if watch_folder:
        folder = Path(watch_folder)
        newest = newest_video_in(folder)
        if newest is None:
            raise FileNotFoundError(
                f"No video files found in watch_folder: {folder}\n"
                "  Point watch_folder at your OBS replay buffer export folder,\n"
                "  or set live_source to the exact replay .mp4 path."
            )
        return newest

    raise FileNotFoundError(
        "No live source configured.\n"
        "  Set live_source to your OBS replay buffer export file, or\n"
        "  set watch_folder to the folder OBS writes replays into, or\n"
        "  pass --source on the CLI."
    )
