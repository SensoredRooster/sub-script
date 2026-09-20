#!/usr/bin/env python3
"""Run every scripts/smoke_*.py in turn and print a PASS/FAIL table.

Usage:  python scripts/smoke_all.py
Exit code is non-zero when any smoke fails. ffmpeg-dependent smokes are
reported as SKIP when no ffmpeg binary can be found.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subscript.runtime_paths import find_ffmpeg  # noqa: E402

NEEDS_FFMPEG = {
    "smoke_reframe",
    "smoke_captions",
    "smoke_music",
    "smoke_highlights",
    "smoke_killfeed",
}


def main() -> int:
    scripts = sorted(p for p in (ROOT / "scripts").glob("smoke_*.py") if p.stem != "smoke_all")
    have_ffmpeg = find_ffmpeg() is not None
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("SUB_SCRIPT_NO_OPEN", "1")
    rows: list[tuple[str, str, float, str]] = []
    failed = 0
    for script in scripts:
        if script.stem in NEEDS_FFMPEG and not have_ffmpeg:
            rows.append((script.name, "SKIP", 0.0, "ffmpeg not found"))
            continue
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        took = time.time() - t0
        if proc.returncode == 0:
            rows.append((script.name, "PASS", took, ""))
        else:
            failed += 1
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            rows.append((script.name, "FAIL", took, " | ".join(tail)))

    width = max(len(r[0]) for r in rows) if rows else 20
    print()
    for name, status, took, note in rows:
        line = f"  {name:<{width}}  {status:<4}  {took:5.1f}s"
        if note:
            line += f"  {note}"
        print(line)
    print()
    print(f"  {len(rows) - failed}/{len(rows)} smoke scripts passed" + ("" if have_ffmpeg else "  (ffmpeg missing: media smokes skipped)"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
