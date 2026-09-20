"""Manual handoff: copy clip into for_<platform>/ + POST_INSTRUCTIONS.txt."""

from __future__ import annotations

import shutil
from pathlib import Path

from subscript.publish.base import PublishMeta, PublishResult


def manual_handoff(
    *,
    platform_key: str,
    display_name: str,
    path: Path,
    meta: PublishMeta,
    instructions: str,
    prefer_vertical: bool = True,
) -> PublishResult:
    """Copy video into ``approved/<id>/for_<platform>/`` and write POST_INSTRUCTIONS.txt."""
    path = Path(path)
    if not path.is_file():
        return PublishResult(
            platform=display_name,
            ok=False,
            status="error",
            message=f"video missing: {path}",
        )

    dest_dir = meta.approved_dir / f"for_{platform_key}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    suffix = path.suffix or ".mp4"
    dest_name = "vertical_captioned" + suffix if prefer_vertical else path.name
    lower = path.name.lower()
    if "horizontal" in lower:
        dest_name = "horizontal" + suffix
    elif "captioned" in lower:
        dest_name = "vertical_captioned" + suffix
    elif "vertical" in lower:
        dest_name = "vertical" + suffix
    dest = dest_dir / dest_name
    shutil.copy2(path, dest)

    instructions_path = dest_dir / "POST_INSTRUCTIONS.txt"
    instructions_path.write_text(instructions.strip() + "\n", encoding="utf-8")

    return PublishResult(
        platform=display_name,
        ok=True,
        status="manual",
        message="manual pack ready",
        folder=str(dest_dir),
        detail={"video": str(dest), "instructions": str(instructions_path)},
    )


def api_not_configured(display_name: str, how_to: str) -> PublishResult:
    return PublishResult(
        platform=display_name,
        ok=False,
        status="not_configured",
        message=how_to,
    )
