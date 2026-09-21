"""Normalized vertical layout templates and media probing.

The composer deliberately stores source regions as fractions of the source frame.
That keeps a creator's template useful when a recorder changes from 1920x1080 to
another compatible landscape resolution.  Rendering remains fail-safe: an absent
or invalid template falls back to the long-standing center crop.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import subprocess
from typing import Any

from subscript.clip import COMPAT_AUDIO, COMPAT_MOVFLAGS, COMPAT_VIDEO, require_ffmpeg, run_ffmpeg
from subscript.runtime_paths import find_ffprobe


REGION_KEYS = ("x", "y", "w", "h")
PRESETS = {
    "gameplay_facecam": {
        "label": "Gameplay + Facecam",
        "gameplay": {"x": 0.0, "y": 0.0, "w": 0.72, "h": 1.0},
        "facecam": {"x": 0.72, "y": 0.0, "w": 0.28, "h": 0.28},
        "gameplay_box": {"x": 0.04, "y": 0.35, "w": 0.92, "h": 0.60},
        "facecam_box": {"x": 0.12, "y": 0.04, "w": 0.76, "h": 0.27},
        "background": "solid",
    },
    "facecam_top": {
        "label": "Facecam Top / Gameplay Bottom",
        "gameplay": {"x": 0.0, "y": 0.0, "w": 0.72, "h": 1.0},
        "facecam": {"x": 0.72, "y": 0.0, "w": 0.28, "h": 0.28},
        "gameplay_box": {"x": 0.04, "y": 0.34, "w": 0.92, "h": 0.61},
        "facecam_box": {"x": 0.12, "y": 0.04, "w": 0.76, "h": 0.25},
        "background": "solid",
    },
    "gameplay_top": {
        "label": "Gameplay Top / Facecam Bottom",
        "gameplay": {"x": 0.0, "y": 0.0, "w": 0.72, "h": 1.0},
        "facecam": {"x": 0.72, "y": 0.0, "w": 0.28, "h": 0.28},
        "gameplay_box": {"x": 0.04, "y": 0.04, "w": 0.92, "h": 0.61},
        "facecam_box": {"x": 0.12, "y": 0.69, "w": 0.76, "h": 0.25},
        "background": "solid",
    },
    "gameplay_only": {
        "label": "Gameplay Only",
        "gameplay": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "facecam": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
        "gameplay_box": {"x": 0.04, "y": 0.18, "w": 0.92, "h": 0.64},
        "facecam_box": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
        "background": "blurred",
    },
    "facecam_overlay": {
        "label": "Facecam Overlay",
        "gameplay": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "facecam": {"x": 0.72, "y": 0.0, "w": 0.28, "h": 0.28},
        "gameplay_box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "facecam_box": {"x": 0.62, "y": 0.06, "w": 0.30, "h": 0.22},
        "background": "blurred",
    },
    "blurred_background": {
        "label": "Blurred Background + Reframed Gameplay",
        "gameplay": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        "facecam": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
        "gameplay_box": {"x": 0.08, "y": 0.22, "w": 0.84, "h": 0.56},
        "facecam_box": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
        "background": "blurred",
    },
}


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_region(value: Any, fallback: dict[str, float]) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    x = max(0.0, min(1.0, _number(raw.get("x"), fallback["x"])))
    y = max(0.0, min(1.0, _number(raw.get("y"), fallback["y"])))
    w = max(0.0, min(1.0 - x, _number(raw.get("w"), fallback["w"])))
    h = max(0.0, min(1.0 - y, _number(raw.get("h"), fallback["h"])))
    return {"x": round(x, 6), "y": round(y, 6), "w": round(w, 6), "h": round(h, 6)}


def normalize_layout(value: Any) -> dict[str, Any]:
    """Return a safe, serializable layout; legacy/empty data means center crop."""
    raw = value if isinstance(value, dict) else {}
    mode = str(raw.get("mode") or "center_crop").strip().lower()
    preset = str(raw.get("preset") or "gameplay_facecam").strip().lower()
    if mode != "composer" or preset not in PRESETS:
        return {"version": 1, "mode": "center_crop", "preset": "center_crop"}
    base = deepcopy(PRESETS[preset])
    regions = raw.get("regions") if isinstance(raw.get("regions"), dict) else raw
    boxes = raw.get("boxes") if isinstance(raw.get("boxes"), dict) else raw
    base["regions"] = {
        "gameplay": normalize_region((regions or {}).get("gameplay"), base["gameplay"]),
        "facecam": normalize_region((regions or {}).get("facecam"), base["facecam"]),
    }
    base["boxes"] = {
        "gameplay": normalize_region((boxes or {}).get("gameplay_box"), base["gameplay_box"]),
        "facecam": normalize_region((boxes or {}).get("facecam_box"), base["facecam_box"]),
    }
    style = raw.get("style") if isinstance(raw.get("style"), dict) else {}
    base["style"] = {
        "background": str(style.get("background") or base["background"]),
        "gap": max(0, min(200, int(_number(style.get("gap"), 18)))),
        "border": max(0, min(32, int(_number(style.get("border"), 0)))),
        "border_color": str(style.get("border_color") or "white@0.86"),
        "zoom": max(1.0, min(3.0, _number(style.get("zoom"), 1.0))),
        "caption_safe_zone": str(style.get("caption_safe_zone") or "bottom"),
    }
    return {
        "version": 1,
        "mode": "composer",
        "preset": preset,
        "regions": base["regions"],
        "boxes": base["boxes"],
        "style": base["style"],
    }


def layout_from_form(values: Any) -> dict[str, Any]:
    """Build a template from the small set of composer controls in an HTML form."""
    def region(prefix: str, fallback: dict[str, float]) -> dict[str, float]:
        raw = {key: values.get(f"{prefix}_{key}") for key in REGION_KEYS}
        return normalize_region(raw, fallback)

    preset = str(values.get("vertical_preset") or "gameplay_facecam")
    base = PRESETS.get(preset) or PRESETS["gameplay_facecam"]
    mode = str(values.get("vertical_layout_mode") or "center_crop")
    if mode != "composer":
        return normalize_layout({})
    return normalize_layout({
        "mode": "composer", "preset": preset,
        "regions": {
            "gameplay": region("gameplay", base["gameplay"]),
            "facecam": region("facecam", base["facecam"]),
        },
        "boxes": {
            "gameplay_box": region("gameplay_box", base["gameplay_box"]),
            "facecam_box": region("facecam_box", base["facecam_box"]),
        },
        "style": {
            "background": values.get("vertical_background") or base["background"],
            "gap": values.get("vertical_gap") or 18,
            "border": values.get("vertical_border") or 0,
            "border_color": values.get("vertical_border_color") or "white@0.86",
            "caption_safe_zone": values.get("caption_safe_zone") or "bottom",
        },
    })


def make_vertical_with_layout(
    source: Path,
    dest: Path,
    *,
    width: int,
    height: int,
    layout: Any,
) -> Path:
    """Render a true WxH vertical output from normalized source regions."""
    normalized = normalize_layout(layout)
    if normalized["mode"] != "composer":
        return _center_crop(source, dest, width, height)
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    regions = normalized["regions"]
    boxes = normalized["boxes"]
    style = normalized["style"]
    background = style["background"]
    gameplay = regions["gameplay"]
    facecam = regions["facecam"]
    game_box = boxes["gameplay"]
    face_box = boxes["facecam"]
    # Keep every crop inside the source and make each tile fit without stretching.
    gx, gy, gw, gh = (gameplay[k] for k in REGION_KEYS)
    bx, by, bw, bh = (game_box[k] for k in REGION_KEYS)
    filters = ["[0:v]split=3[base][game][face]"]
    if background == "blurred":
        filters.append(f"[base]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=18:2[bg]")
    else:
        filters.append(f"color=c=0x111713:s={width}x{height}[bg]")
    game_w, game_h, game_x, game_y = max(2, int(width * bw)), max(2, int(height * bh)), int(width * bx), int(height * by)
    game_crop = f"crop=iw*{gw}:ih*{gh}:iw*{gx}:ih*{gy}"
    game_tile = f"[game]{game_crop},scale={game_w}:{game_h}:force_original_aspect_ratio=increase,crop={game_w}:{game_h}"
    if style["border"]:
        game_tile += f",drawbox=x=0:y=0:w=iw:h=ih:color={style['border_color']}:t={style['border']}"
    filters.append(game_tile + "[game_tile]")
    filters.append(f"[bg][game_tile]overlay={game_x}:{game_y}:shortest=1[composed]")
    current = "composed"
    fx, fy, fw, fh = (facecam[k] for k in REGION_KEYS)
    fbx, fby, fbw, fbh = (face_box[k] for k in REGION_KEYS)
    if fw > 0.001 and fh > 0.001 and fbw > 0.001 and fbh > 0.001:
        face_w, face_h, face_x, face_y = max(2, int(width * fbw)), max(2, int(height * fbh)), int(width * fbx), int(height * fby)
        gap = int(style.get("gap") or 0)
        if face_y + face_h <= game_y:
            face_h = max(2, face_h - gap // 2)
            game_y += gap // 2
            game_h = max(2, game_h - gap // 2)
        elif game_y + game_h <= face_y:
            game_h = max(2, game_h - gap // 2)
            face_y += gap // 2
            face_h = max(2, face_h - gap // 2)
        face_tile = f"[face]crop=iw*{fw}:ih*{fh}:iw*{fx}:ih*{fy},scale={face_w}:{face_h}:force_original_aspect_ratio=increase,crop={face_w}:{face_h}"
        if style["border"]:
            face_tile += f",drawbox=x=0:y=0:w=iw:h=ih:color={style['border_color']}:t={style['border']}"
        filters.append(face_tile + "[face_tile]")
        filters.append(f"[{current}][face_tile]overlay={face_x}:{face_y}:shortest=1,setsar=1[outv]")
    else:
        filters[-1] = filters[-1].replace("[composed]", "[outv]").replace("[outv]", ",setsar=1[outv]")
    cmd = [
        ffmpeg, "-y", "-i", str(source), "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-map", "0:a?", "-r", "30", *COMPAT_VIDEO,
        *COMPAT_AUDIO, *COMPAT_MOVFLAGS, str(dest),
    ]
    try:
        run_ffmpeg(cmd, what="ffmpeg vertical layout")
    except RuntimeError:
        # Some older Windows FFmpeg builds do not accept optional audio mapping.
        cmd[cmd.index("0:a?")] = "0:a"
        run_ffmpeg(cmd, what="ffmpeg vertical layout")
    return dest


def _center_crop(source: Path, dest: Path, width: int, height: int) -> Path:
    ffmpeg = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    run_ffmpeg([ffmpeg, "-y", "-i", str(source), "-vf", vf, *COMPAT_VIDEO, *COMPAT_AUDIO, *COMPAT_MOVFLAGS, str(dest)], what="ffmpeg vertical")
    return dest


def probe_media(path: Path) -> dict[str, Any]:
    """Read dimensions/aspect/rotation/audio/fps without exposing file contents."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return {}
    cmd = [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        payload = json.loads(proc.stdout or "{}")
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video:
        # ffprobe can successfully parse a container while finding no streams;
        # callers should retain their existing fail-soft/mocked behavior here.
        return {}
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    rotation = (video.get("tags") or {}).get("rotate") or (video.get("side_data_list") or [{}])[0].get("rotation", 0)
    try:
        rotation = int(rotation)
    except (TypeError, ValueError):
        rotation = 0
    return {
        "width": width, "height": height, "display_aspect_ratio": video.get("display_aspect_ratio"),
        "sample_aspect_ratio": video.get("sample_aspect_ratio"), "rotation": rotation,
        "avg_frame_rate": video.get("avg_frame_rate"), "pix_fmt": video.get("pix_fmt"),
        "has_audio": bool(audio), "duration": float((payload.get("format") or {}).get("duration") or 0),
    }


def aspect_ratio(metadata: dict[str, Any]) -> float:
    width, height = int(metadata.get("width") or 0), int(metadata.get("height") or 0)
    return width / height if width and height else 0.0
