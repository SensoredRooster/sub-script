#!/usr/bin/env python3
"""Smoke-import packaging helpers (no Windows / PyInstaller required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from subscript.runtime_paths import (
        app_dir,
        find_ffmpeg,
        ffmpeg_install_hint,
        is_frozen,
        resource_dir,
    )
    from subscript.clip import COMPAT_AUDIO, COMPAT_VIDEO, require_ffmpeg
    from subscript import config as cfg_mod

    assert is_frozen() is False
    assert app_dir() == ROOT
    assert resource_dir() == ROOT
    assert COMPAT_VIDEO and COMPAT_AUDIO
    assert "ffmpeg.exe" in ffmpeg_install_hint() or "ffmpeg" in ffmpeg_install_hint()
    # find_ffmpeg may be None on this Linux box — that is fine
    _ = find_ffmpeg()
    assert cfg_mod.ROOT == ROOT
    assert hasattr(cfg_mod, "load_config")
    # require_ffmpeg either returns a path or raises with beside-app hint
    try:
        path = require_ffmpeg()
        print(f"require_ffmpeg -> {path}")
    except RuntimeError as exc:
        msg = str(exc)
        assert "beside the app" in msg or "PATH" in msg
        print("require_ffmpeg raised expected hint (no ffmpeg on this machine)")
    print("smoke_windows_packaging: OK")


if __name__ == "__main__":
    main()
