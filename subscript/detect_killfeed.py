"""Experimental v0: Warzone/CoD kill-feed OCR (optional engines).

Samples VOD frames with ffmpeg, crops a configurable ROI (fractions of the
stream frame — locked to ``stream.resolution`` when set), and looks for the
user's **exact** in-game player name in OCR text so other players' kills do
not fire.

OCR is optional: try ``easyocr`` then ``pytesseract``. If neither is installed,
callers get an empty kill list plus a clear note — the app still runs on
loudness-only highlights.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from subscript.clip import require_ffmpeg

# Default Warzone-ish kill feed: top-right portion of a 16:9 HUD.
_DEFAULT_ROI = {"x": 0.62, "y": 0.02, "w": 0.36, "h": 0.28}


def detect_enabled(cfg: dict[str, Any] | None) -> bool:
    """True only when ``detect.enabled`` is explicitly true."""
    if not cfg:
        return False
    det = cfg.get("detect")
    if isinstance(det, dict):
        return bool(det.get("enabled"))
    return False


def resolve_player_name(cfg: dict[str, Any] | None) -> str:
    """Exact in-game name: ``detect.player_name`` or ``stream.player_name``."""
    if not cfg:
        return ""
    det = cfg.get("detect") if isinstance(cfg.get("detect"), dict) else {}
    name = str(det.get("player_name") or "").strip()
    if name:
        return name
    stream = cfg.get("stream") if isinstance(cfg.get("stream"), dict) else {}
    return str(stream.get("player_name") or "").strip()


def resolve_roi(cfg: dict[str, Any] | None) -> dict[str, float]:
    """Return ROI as fractions of frame width/height (0..1), clamped."""
    roi = dict(_DEFAULT_ROI)
    if cfg and isinstance(cfg.get("detect"), dict):
        raw = cfg["detect"].get("roi")
        if isinstance(raw, dict):
            for key in ("x", "y", "w", "h"):
                if key in raw:
                    try:
                        roi[key] = float(raw[key])
                    except (TypeError, ValueError):
                        pass
    x = min(1.0, max(0.0, float(roi["x"])))
    y = min(1.0, max(0.0, float(roi["y"])))
    w = min(1.0 - x, max(0.01, float(roi["w"])))
    h = min(1.0 - y, max(0.01, float(roi["h"])))
    return {"x": x, "y": y, "w": w, "h": h}


def resolve_stream_size(cfg: dict[str, Any] | None) -> tuple[int, int] | None:
    """Parse ``stream.resolution`` like ``1920x1080`` → (w, h), or None."""
    if not cfg:
        return None
    stream = cfg.get("stream") if isinstance(cfg.get("stream"), dict) else {}
    raw = str(stream.get("resolution") or "").strip().lower()
    m = re.match(r"^(\d+)\s*[x×]\s*(\d+)$", raw)
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    if w < 16 or h < 16:
        return None
    return w, h


def sample_fps(cfg: dict[str, Any] | None) -> float:
    if cfg and isinstance(cfg.get("detect"), dict):
        try:
            fps = float(cfg["detect"].get("sample_fps") or 1.0)
            return max(0.1, min(10.0, fps))
        except (TypeError, ValueError):
            pass
    return 1.0


def ocr_engines_available() -> dict[str, bool]:
    easy = False
    tess = False
    try:
        import easyocr  # noqa: F401
        easy = True
    except Exception:
        easy = False
    try:
        import pytesseract  # noqa: F401
        tess = True
    except Exception:
        tess = False
    return {"easyocr": easy, "pytesseract": tess}


def ocr_available() -> bool:
    return any(ocr_engines_available().values())


def roi_pixel_box(frame_w: int, frame_h: int, roi: dict[str, float]) -> tuple[int, int, int, int]:
    x0 = int(round(frame_w * float(roi["x"])))
    y0 = int(round(frame_h * float(roi["y"])))
    rw = max(1, int(round(frame_w * float(roi["w"]))))
    rh = max(1, int(round(frame_h * float(roi["h"]))))
    x0 = min(max(0, x0), max(0, frame_w - 1))
    y0 = min(max(0, y0), max(0, frame_h - 1))
    rw = min(rw, frame_w - x0)
    rh = min(rh, frame_h - y0)
    return x0, y0, max(1, rw), max(1, rh)


def probe_video_size(source: Path) -> tuple[int, int]:
    ffmpeg = require_ffmpeg()
    ffprobe = shutil.which("ffprobe") or ffmpeg.replace("ffmpeg", "ffprobe")
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(source)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode == 0:
        text = (proc.stdout or "").strip().splitlines()
        if text:
            m = re.match(r"^(\d+)x(\d+)", text[0].strip())
            if m:
                return int(m.group(1)), int(m.group(2))
    raise RuntimeError("ffprobe could not read video size")


def sample_roi_frames(
    source: Path, out_dir: Path, *, roi: dict[str, float] | None = None,
    fps: float = 1.0, frame_size: tuple[int, int] | None = None, max_frames: int = 120,
) -> list[tuple[float, Path]]:
    source = Path(source)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    roi = resolve_roi({"detect": {"roi": roi}} if roi else None) if roi else resolve_roi(None)
    if frame_size is None:
        frame_size = probe_video_size(source)
    fw, fh = frame_size
    x, y, w, h = roi_pixel_box(fw, fh, roi)
    ffmpeg = require_ffmpeg()
    fps = max(0.1, float(fps))
    pattern = out_dir / "roi_%06d.png"
    vf = f"fps={fps},crop={w}:{h}:{x}:{y}"
    cmd = [ffmpeg, "-y", "-hide_banner", "-nostats", "-i", str(source), "-vf", vf, "-frames:v", str(max(1, int(max_frames))), str(pattern)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        tail = "\n".join(err.splitlines()[-20:]) if err else "(no ffmpeg output)"
        raise RuntimeError(f"ffmpeg ROI sample failed:\n{tail}")
    frames: list[tuple[float, Path]] = []
    for i, path in enumerate(sorted(out_dir.glob("roi_*.png"))):
        frames.append((i / fps, path))
    return frames


def _normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def player_name_in_text(ocr_text: str, player_name: str) -> bool:
    """Exact in-game name token match (case-insensitive); other players do not fire."""
    name = (player_name or "").strip()
    if not name:
        return False
    hay = _normalize_ocr_text(ocr_text)
    if not hay:
        return False
    escaped = re.escape(name)
    pat = re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
    return pat.search(hay) is not None


def _ocr_image(path: Path) -> str:
    engines = ocr_engines_available()
    if engines.get("easyocr"):
        try:
            import easyocr  # type: ignore[import-untyped]
            reader = getattr(_ocr_image, "_easy_reader", None)
            if reader is None:
                reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                setattr(_ocr_image, "_easy_reader", reader)
            parts = reader.readtext(str(path), detail=0, paragraph=True)
            return _normalize_ocr_text(" ".join(str(p) for p in parts))
        except Exception as exc:  # noqa: BLE001
            if not engines.get("pytesseract"):
                raise RuntimeError(f"easyocr failed: {exc}") from exc
    if engines.get("pytesseract"):
        from PIL import Image  # type: ignore[import-untyped]
        import pytesseract  # type: ignore[import-untyped]
        return _normalize_ocr_text(pytesseract.image_to_string(Image.open(path)) or "")
    raise RuntimeError(
        "OCR engine not installed. Optional: pip install -r requirements-ocr.txt "
        "(and install system tesseract if using pytesseract)."
    )


def detect_kills(
    source: Path, *, player_name: str, cfg: dict[str, Any] | None = None, work_dir: Path | None = None,
) -> dict[str, Any]:
    """Detect kill-feed moments for exact player_name. Empty + note if OCR missing."""
    source = Path(source)
    name = (player_name or "").strip()
    roi = resolve_roi(cfg)
    fps = sample_fps(cfg)
    locked = resolve_stream_size(cfg)
    note = ""
    if not name:
        return {"kills": [], "note": "detect.player_name / stream.player_name is empty — skip kill-feed.", "ocr": ocr_available(), "roi": roi, "frame_size": list(locked) if locked else None}
    if not ocr_available():
        frame_size = locked
        if work_dir is not None and source.is_file():
            try:
                if frame_size is None:
                    frame_size = probe_video_size(source)
                sample_roi_frames(source, Path(work_dir), roi=roi, fps=fps, frame_size=frame_size, max_frames=12)
            except Exception as exc:  # noqa: BLE001
                note = f"ROI sample note: {exc}. "
        return {
            "kills": [],
            "note": note + "OCR engine not installed — kill-feed detection skipped (loudness-only). Optional: pip install -r requirements-ocr.txt and/or install system tesseract for pytesseract.",
            "ocr": False, "roi": roi, "frame_size": list(frame_size) if frame_size else None,
        }
    own_tmp = work_dir is None
    tmp_root = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="killfeed_"))
    try:
        frame_size = locked if locked is not None else probe_video_size(source)
        frames = sample_roi_frames(source, tmp_root, roi=roi, fps=fps, frame_size=frame_size)
        kills: list[dict[str, Any]] = []
        last_t = -999.0
        min_gap = max(0.5, 1.0 / fps)
        for t, path in frames:
            try:
                text = _ocr_image(path)
            except Exception:
                continue
            if not player_name_in_text(text, name):
                continue
            if t - last_t < min_gap:
                continue
            kills.append({"t": round(float(t), 3), "text": text[:200]})
            last_t = t
        return {"kills": kills, "note": note or "", "ocr": True, "roi": roi, "frame_size": list(frame_size)}
    except Exception as exc:  # noqa: BLE001
        return {"kills": [], "note": f"Kill-feed detection failed ({exc}); using loudness-only.", "ocr": True, "roi": roi, "frame_size": list(locked) if locked else None}
    finally:
        if own_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)


def kills_to_suggestions(kills: list[dict[str, Any]], *, buffer_seconds: float = 30.0, pre_roll: float = 8.0) -> list[dict[str, Any]]:
    dur = max(1.0, float(buffer_seconds))
    pre = max(0.0, float(pre_roll))
    out: list[dict[str, Any]] = []
    for k in kills:
        t = float(k.get("t") or 0.0)
        out.append({"start": round(max(0.0, t - pre), 3), "duration": round(dur, 3), "score": 1.0, "source": "killfeed"})
    return out


def merge_highlight_suggestions(
    loudness: list[dict[str, Any]], killfeed: list[dict[str, Any]], *, top_n: int = 5, mode: str = "merge",
) -> list[dict[str, Any]]:
    top_n = max(1, int(top_n))
    mode = (mode or "merge").strip().lower()
    if mode == "replace" and killfeed:
        combined = [dict(s) for s in killfeed]
    else:
        combined = [dict(s) for s in loudness] + [dict(s) for s in killfeed]
        for s in combined:
            s.setdefault("source", "loudness")
    combined.sort(key=lambda s: (-float(s.get("score") or 0.0), 0 if s.get("source") == "killfeed" else 1, float(s.get("start") or 0.0)))
    picked: list[dict[str, Any]] = []
    for s in combined:
        start = float(s.get("start") if s.get("start") is not None else 0.0)
        dur = float(s.get("duration") or 30.0)
        end = start + dur
        overlap = False
        for p in picked:
            p0 = float(p["start"])
            p1 = p0 + float(p["duration"])
            if start < p1 and end > p0:
                overlap = True
                break
        if overlap:
            continue
        picked.append({"start": round(start, 3), "duration": round(dur, 3), "score": round(float(s.get("score") or 0.0), 4), "source": s.get("source") or "loudness"})
        if len(picked) >= top_n:
            break
    picked.sort(key=lambda p: float(p["start"]))
    return picked
