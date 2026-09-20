"""Local publish handoff: copy approved assets and open the folder."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def publish_local(
    *,
    item_id: str,
    title: str,
    paths: list[Path],
    out_dir: Path,
) -> dict[str, Any]:
    approved = out_dir / "approved" / item_id
    approved.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for src in paths:
        if not src or not Path(src).exists():
            continue
        src = Path(src)
        dest = approved / src.name
        shutil.copy2(src, dest)
        saved.append(str(dest))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    meta = {
        "approved_at": stamp,
        "item_id": item_id,
        "title": title,
        "files": saved,
        "note": (
            "Saved locally. Social upload (YouTube/TikTok/IG/X/Rumble/FB) "
            "hooks in next — Approve will post these same files."
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
