"""Resolve project / frozen-app directories and sidecar tools (ffmpeg)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Writable app folder: next to SubScript.exe when frozen, else repo root.

    End users keep ``config.yaml``, ``out/``, ``assets/``, and ``ffmpeg.exe``
    here so a double-click works without hunting PATH.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_dir() -> Path:
    """Read-only bundled resources (PyInstaller ``_MEIPASS`` / package tree)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def chdir_app() -> Path:
    """Make cwd the app folder so relative config/out paths stay next to the exe."""
    root = app_dir()
    try:
        os.chdir(root)
    except OSError:
        pass
    return root


def find_ffmpeg() -> str | None:
    """Prefer ffmpeg.exe beside the app (onedir bundle), then PATH.

    Search order:
      1. ``<app_dir>/ffmpeg.exe``
      2. ``<app_dir>/ffmpeg/bin/ffmpeg.exe`` (full zip layout)
      3. ``<app_dir>/bin/ffmpeg.exe``
      4. ``PATH`` (``ffmpeg`` / ``ffmpeg.exe``)
    """
    root = app_dir()
    candidates = [
        root / "ffmpeg.exe",
        root / "ffmpeg" / "bin" / "ffmpeg.exe",
        root / "bin" / "ffmpeg.exe",
        root / "ffmpeg",
        root / "ffmpeg" / "bin" / "ffmpeg",
        root / "bin" / "ffmpeg",
    ]
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    return shutil.which("ffmpeg")


def find_ffprobe(ffmpeg_path: str | None = None) -> str | None:
    """Locate ffprobe: beside the app, then next to the resolved ffmpeg binary, then PATH.

    ffprobe is optional (duration / frame-size probing has fallbacks) but ships in
    every ffmpeg zip, so users are told to copy both binaries beside the app.
    """
    root = app_dir()
    candidates = [
        root / "ffprobe.exe",
        root / "ffmpeg" / "bin" / "ffprobe.exe",
        root / "bin" / "ffprobe.exe",
        root / "ffprobe",
        root / "ffmpeg" / "bin" / "ffprobe",
        root / "bin" / "ffprobe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    ffmpeg = ffmpeg_path or find_ffmpeg()
    if ffmpeg:
        exe = Path(ffmpeg)
        # Swap only the basename (``C:/ffmpeg/bin/ffmpeg.exe`` -> ``.../ffprobe.exe``),
        # never every "ffmpeg" in the directory part.
        sibling = exe.with_name(exe.name.replace("ffmpeg", "ffprobe", 1))
        if sibling != exe and sibling.is_file():
            return str(sibling.resolve())
    return shutil.which("ffprobe")


def ffmpeg_install_hint() -> str:
    root = app_dir()
    lines = [
        "ffmpeg not found beside the app or on PATH.",
        "  Easiest (recommended for the .exe):",
        "    1. Download a Windows ffmpeg build (essentials zip)",
        "    2. Copy ffmpeg.exe (and ffprobe.exe) into this folder:",
        f"         {root}\\ffmpeg.exe",
        "    3. Double-click SubScript.exe again",
        "  Or install system-wide, then reopen the app:",
        "    winget install ffmpeg",
        "    choco install ffmpeg",
        "  Confirm: ffmpeg -version",
        "  More: https://ffmpeg.org/download.html",
    ]
    return "\n".join(lines)
