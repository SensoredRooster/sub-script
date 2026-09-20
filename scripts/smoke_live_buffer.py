"""Smoke: live source resolve (watch folder / file) without ffmpeg."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from subscript.buffer import newest_video_in, resolve_live_source  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        older = folder / "old.mp4"
        newer = folder / "new.mp4"
        older.write_bytes(b"old")
        newer.write_bytes(b"new")
        # bump mtime
        import os
        import time

        os.utime(older, (time.time() - 100, time.time() - 100))
        os.utime(newer, None)
        assert newest_video_in(folder) == newer
        got = resolve_live_source({"watch_folder": str(folder)})
        assert got == newer
        got2 = resolve_live_source({"live_source": str(newer)})
        assert got2 == newer
        print("smoke_live_buffer: OK")


if __name__ == "__main__":
    main()
