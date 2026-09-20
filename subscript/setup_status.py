"""Setup checklist: green / yellow / red rows for the app home page."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _item(
    id_: str,
    label: str,
    status: str,
    detail: str,
    fix: str,
) -> dict[str, str]:
    return {
        "id": id_,
        "label": label,
        "status": status,  # green | yellow | red
        "detail": detail,
        "fix": fix,
    }


def _root() -> Path:
    try:
        from subscript.runtime_paths import app_dir

        return app_dir()
    except Exception:
        return Path(__file__).resolve().parents[1]


def _ffmpeg_row() -> dict[str, str]:
    path = None
    try:
        from subscript.runtime_paths import find_ffmpeg

        path = find_ffmpeg()
    except Exception:
        path = None
    if path:
        return _item(
            "ffmpeg",
            "ffmpeg",
            "green",
            f"Found: {path}",
            "Ready — clips can encode.",
        )
    return _item(
        "ffmpeg",
        "ffmpeg",
        "red",
        "Not found beside the app or on PATH.",
        "Copy ffmpeg.exe next to the app, or winget install ffmpeg, then reopen.",
    )


def _config_row(root: Path) -> dict[str, str]:
    cfg = root / "config.yaml"
    if cfg.is_file():
        return _item(
            "config",
            "config.yaml",
            "green",
            f"Present: {cfg.name}",
            "Ready — settings load from this file.",
        )
    return _item(
        "config",
        "config.yaml",
        "red",
        "Missing config.yaml.",
        "Copy config.example.yaml to config.yaml (or just run run-app.bat once).",
    )


def _logo_row(cfg: dict[str, Any], root: Path) -> dict[str, str]:
    brand = cfg.get("brand") if isinstance(cfg.get("brand"), dict) else {}
    rel = (brand.get("logo_path") or "assets/logo.png").strip() or "assets/logo.png"
    path = Path(rel)
    if not path.is_absolute():
        path = root / path
    if path.is_file() and path.stat().st_size > 0:
        return _item(
            "logo",
            "Logo",
            "green",
            f"Found: {rel}",
            "Ready — watermark will appear on clips.",
        )
    return _item(
        "logo",
        "Logo",
        "yellow",
        f"No logo at {rel}.",
        "Upload a PNG in Branding, or drop assets/logo.png.",
    )


def _live_row(cfg: dict[str, Any]) -> dict[str, str]:
    live = (cfg.get("live_source") or "").strip()
    watch = (cfg.get("watch_folder") or "").strip()
    if live or watch:
        where = live or watch
        return _item(
            "live",
            "Live / hotkey source",
            "green",
            f"Configured: {where}",
            "Ready — Start watcher on the Live card when you stream.",
        )
    return _item(
        "live",
        "Live / hotkey source",
        "yellow",
        "live_source and watch_folder are empty.",
        "Set live_source or watch_folder in config.yaml (OBS replay path).",
    )


def _youtube_row(cfg: dict[str, Any]) -> dict[str, str]:
    yt = cfg.get("youtube") if isinstance(cfg.get("youtube"), dict) else {}
    platforms = cfg.get("platforms") if isinstance(cfg.get("platforms"), dict) else {}
    plat_yt = platforms.get("youtube") if isinstance(platforms.get("youtube"), dict) else {}
    enabled = bool(yt.get("enabled")) or bool(plat_yt.get("enabled"))
    if not enabled:
        return _item(
            "youtube",
            "YouTube",
            "green",
            "Dry-run — upload disabled (local pack only).",
            "Safe for testing. Enable later via Connect YouTube in the README.",
        )
    secrets = None
    try:
        from subscript.upload import client_secrets_path

        secrets = client_secrets_path(yt)
    except Exception:
        raw = (yt.get("client_secrets_file") or "credentials.json").strip()
        secrets = _root() / raw
    if secrets and Path(secrets).is_file():
        return _item(
            "youtube",
            "YouTube",
            "green",
            f"Enabled; secrets at {Path(secrets).name}.",
            "Ready — Approve can upload Shorts after OAuth.",
        )
    return _item(
        "youtube",
        "YouTube",
        "red",
        "Enabled but credentials.json (OAuth client) is missing.",
        "Follow Connect YouTube in the README; save OAuth JSON as credentials.json.",
    )


def _captions_row(cfg: dict[str, Any]) -> dict[str, str]:
    caps = cfg.get("captions") if isinstance(cfg.get("captions"), dict) else {}
    engine = str(caps.get("engine") or "auto").strip().lower()
    enabled = True if "enabled" not in caps else bool(caps.get("enabled"))
    whisper = False
    try:
        from subscript.captions import whisper_available

        whisper = bool(whisper_available())
    except Exception:
        try:
            import faster_whisper  # noqa: F401

            whisper = True
        except Exception:
            whisper = False
    if not enabled:
        return _item(
            "captions",
            "Captions engine",
            "yellow",
            "Captions disabled in config.",
            "Turn Captions on in Branding if you want burned-in text.",
        )
    if engine == "demo":
        return _item(
            "captions",
            "Captions engine",
            "green",
            "Demo SRT (placeholder Clip | SUB).",
            "Optional: pip install -r requirements-whisper.txt for real speech.",
        )
    if whisper:
        return _item(
            "captions",
            "Captions engine",
            "green",
            f"Engine {engine} — Whisper installed.",
            "Ready — timed speech captions when encoding.",
        )
    if engine == "whisper":
        return _item(
            "captions",
            "Captions engine",
            "yellow",
            "Engine whisper but faster-whisper not installed (falls back to demo).",
            "pip install -r requirements-whisper.txt",
        )
    return _item(
        "captions",
        "Captions engine",
        "yellow",
        "Auto/demo — Whisper not installed (demo SRT).",
        "Optional: pip install -r requirements-whisper.txt for real speech.",
    )


def _music_row(cfg: dict[str, Any], root: Path) -> dict[str, str]:
    music = cfg.get("music") if isinstance(cfg.get("music"), dict) else {}
    enabled = True if "enabled" not in music else bool(music.get("enabled"))
    path = None
    try:
        from subscript.music import resolve_music_path

        path = resolve_music_path(cfg)
    except Exception:
        rel = (music.get("path") or "assets/music.mp3").strip()
        cand = Path(rel)
        if not cand.is_absolute():
            cand = root / cand
        path = cand if cand.is_file() and cand.stat().st_size > 0 else None
    if not enabled:
        return _item(
            "music",
            "Music bed",
            "yellow",
            "Music bed disabled.",
            "Enable Music bed in Branding if you want a quiet underlay.",
        )
    if path:
        return _item(
            "music",
            "Music bed",
            "green",
            f"Found: {path.name}",
            "Ready — quiet bed mixes under H+V.",
        )
    return _item(
        "music",
        "Music bed",
        "yellow",
        "No music file (mix skipped).",
        "Upload an MP3 in Branding or add assets/music.mp3.",
    )


def _detect_row(cfg: dict[str, Any]) -> dict[str, str]:
    det = cfg.get("detect") if isinstance(cfg.get("detect"), dict) else {}
    enabled = bool(det.get("enabled"))
    if not enabled:
        return _item(
            "detect",
            "Detect / OCR (optional)",
            "green",
            "Off — loudness-only highlights (recommended).",
            "Optional later: enable detect in config.yaml for kill-feed OCR.",
        )
    name = (det.get("player_name") or "").strip()
    stream = cfg.get("stream") if isinstance(cfg.get("stream"), dict) else {}
    if not name:
        name = (stream.get("player_name") or "").strip()
    ocr = False
    engine = "none"
    for mod, label in (("easyocr", "easyocr"), ("pytesseract", "pytesseract")):
        try:
            __import__(mod)
            ocr = True
            engine = label
            break
        except Exception:
            continue
    if not name:
        return _item(
            "detect",
            "Detect / OCR (optional)",
            "yellow",
            "Enabled but player_name is empty.",
            "Set detect.player_name (exact in-game ID) in config.yaml.",
        )
    if ocr:
        return _item(
            "detect",
            "Detect / OCR (optional)",
            "green",
            f"Enabled for {name!r}; OCR via {engine}.",
            "Ready — kill-feed may merge with loudness (experimental).",
        )
    return _item(
        "detect",
        "Detect / OCR (optional)",
        "yellow",
        f"Enabled for {name!r}; no OCR engine (loudness-only).",
        "Optional: pip install -r requirements-ocr.txt (+ Tesseract if needed).",
    )


def collect_setup_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return checklist payload for GET /setup/status and the home card."""
    root = _root()
    if cfg is None:
        try:
            from subscript.config import load_config

            cfg = load_config()
        except Exception:
            cfg = {}
    items = [
        _ffmpeg_row(),
        _config_row(root),
        _logo_row(cfg, root),
        _live_row(cfg),
        _youtube_row(cfg),
        _captions_row(cfg),
        _music_row(cfg, root),
        _detect_row(cfg),
    ]
    counts = {"green": 0, "yellow": 0, "red": 0}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    if counts["red"]:
        summary = f"{counts['red']} need fixing before things feel solid."
    elif counts["yellow"]:
        summary = f"{counts['yellow']} optional gaps — app still works."
    else:
        summary = "All checks look good."
    return {"items": items, "summary": summary, "counts": counts}
