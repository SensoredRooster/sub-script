"""Local social pack: copy approved assets and open the folder."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PLATFORMS = [
    "YouTube Shorts",
    "TikTok",
    "Instagram Reels",
    "Facebook",
    "X",
    "Rumble",
]


def publish_local(
    *,
    item_id: str,
    title: str,
    out_dir: Path,
    horizontal: Path | None = None,
    vertical: Path | None = None,
    vertical_captioned: Path | None = None,
    master: Path | None = None,
    paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Create ``out/approved/<id>/`` with standard social filenames + PLATFORMS.txt.

    Preferred: pass ``horizontal`` / ``vertical`` / ``vertical_captioned``.
    Legacy: ``paths`` list is still copied under original basenames.
    """
    approved = out_dir / "approved" / item_id
    approved.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    named: list[tuple[Path | None, str]] = [
        (horizontal, "horizontal.mp4"),
        (vertical, "vertical.mp4"),
        (vertical_captioned, "vertical_captioned.mp4"),
        (master, "master.mp4"),
    ]
    for src, name in named:
        if not src:
            continue
        src = Path(src)
        if not src.exists():
            continue
        dest = approved / name
        shutil.copy2(src, dest)
        saved.append(str(dest))

    if paths:
        for src in paths:
            if not src or not Path(src).exists():
                continue
            src = Path(src)
            dest = approved / src.name
            if dest.exists():
                continue
            shutil.copy2(src, dest)
            saved.append(str(dest))

    platforms_path = approved / "PLATFORMS.txt"
    platforms_path.write_text(
        "Social export pack - upload-ready files for:\n"
        + "\n".join(f"- {p}" for p in _PLATFORMS)
        + "\n",
        encoding="utf-8",
    )
    saved.append(str(platforms_path))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "approved_at": stamp,
        "item_id": item_id,
        "title": title,
        "files": saved,
        "platforms": _PLATFORMS,
        "note": (
            "Saved locally. Enabled platforms under config platforms: fan out on "
            "Approve (YouTube live API when youtube.enabled / platforms.youtube.enabled; "
            "others default to for_<platform>/ + POST_INSTRUCTIONS.txt)."
        ),
    }
    (approved / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    try:
        if sys.platform.startswith("win"):
            os.startfile(approved)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(approved)], check=False)
        else:
            subprocess.run(["xdg-open", str(approved)], check=False)
    except Exception:
        pass

    return meta
