# -*- mode: python ; coding: utf-8 -*-
# PyInstaller (6.x) onedir build for SubScript.exe (Windows).
# Run via: scripts\build_windows.bat
#
# Output: dist/SubScript/SubScript.exe
# Place ffmpeg.exe + ffprobe.exe beside SubScript.exe (see scripts/FFMPEG_BESIDE_APP.txt).

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("subscript/static", "subscript/static"),
    ("config.example.yaml", "."),
    ("scripts/FFMPEG_BESIDE_APP.txt", "."),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # python-multipart: new import name first, legacy shim second.
    "python_multipart",
    "multipart",
    "yaml",
    "pynput",
    "pynput.keyboard",
    "pynput.keyboard._win32",
    "pynput.mouse",
    "pynput.mouse._win32",
    "googleapiclient",
    "google_auth_oauthlib",
    "google.auth",
    "google.oauth2",
]

# Collect FastAPI / Starlette / Uvicorn package data + submodules.
for pkg in ("uvicorn", "fastapi", "starlette"):
    try:
        d, _b, h = collect_all(pkg)
        datas += d
        hiddenimports += h
    except Exception:
        pass

# Every subscript module (routes are registered via imports the analyser cannot see).
hiddenimports += collect_submodules("subscript")

a = Analysis(
    ["scripts/run_exe.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Optional heavy extras are never bundled; users pip-install them into a venv build.
    excludes=["faster_whisper", "easyocr", "pytesseract", "torch", "PIL", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir
    name="SubScript",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep console for first-run ffmpeg / errors (for-dummies)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SubScript",
)
