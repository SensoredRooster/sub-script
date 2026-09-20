"""PyInstaller entry: double-click opens the review UI (--app).

When frozen, cwd becomes the folder next to SubScript.exe so config.yaml,
out/, assets/, and ffmpeg.exe all live beside the binary (onedir layout).
"""

from __future__ import annotations

import sys

from subscript.runtime_paths import chdir_app, find_ffmpeg, ffmpeg_install_hint, is_frozen


def main() -> None:
    chdir_app()
    # Double-click / no args → desktop app (browser review UI)
    if is_frozen() and len(sys.argv) == 1:
        sys.argv.append("--app")

    # Startup check — prefer ffmpeg beside the exe (not PATH-only)
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        print(f"ffmpeg: {ffmpeg}")
    else:
        print()
        print("WARNING: ffmpeg missing — clipping will fail until you add it.")
        print(ffmpeg_install_hint())
        print()

    from subscript.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
