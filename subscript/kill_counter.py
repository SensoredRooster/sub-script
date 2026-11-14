"""Kill-counter highlight detection — finds YOUR kills, ranks them first.

Watches the in-game kill counter (top-right HUD stack) instead of guessing
from noise: ffmpeg samples the counter region, the bundled tesseract engine
reads the number, and every confirmed increment becomes a kill moment. Menu
screens are rejected with a skull-icon template check so lobby/loadout pages
never produce clips.

Everything runs inside the installer: tesseract ships under
``tesseract/`` next to SubScript.exe (no extra software for testers), frames
are decoded from ffmpeg's raw pipe (no PIL), and the icon check is pure
Python. If the engine is missing or anything fails, callers get an empty
kill list plus a note — loudness highlights still work.

Config (all optional)::

    detect:
      kill_counter: true          # default on; false disables
      counter_roi: {x, y, w, h}   # fractions of frame (default: Warzone 1080p)
      counter_sample_fps: 0.5     # counter reads per second
      tesseract_path: "..."       # explicit override
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from subscript.runtime_paths import app_dir, find_ffprobe, find_ffmpeg, resource_dir

# Warzone HUD @1920x1080: skull icon + kill count block, x1810..1880, y50..115.
_DEFAULT_ROI = {"x": 1810 / 1920, "y": 50 / 1080, "w": 70 / 1920, "h": 65 / 1080}
# Sub-boxes as fractions of the ROI crop: skull icon and the digits below it.
_ICON_BOX = (22 / 70, 0 / 65, 28 / 70, 28 / 65)   # x, y, w, h
_DIGIT_BOX = (0 / 70, 18 / 65, 55 / 70, 45 / 65)
_SCALE = 4  # lanczos upscale before OCR (matches the proven offline scan)
_TEMPLATE_NAME = "kill_icon_warzone.pgm"
_TEMPLATE_SIZE = 28
_ICON_NCC_MIN = 0.85  # skull present: ~0.97+; spectate/countdown HUD: ~0.6-0.8; menus: <0.5
_OCR_ARGS = ("--psm", "7", "-c", "tessedit_char_whitelist=0123456789")

LogFn = Callable[[str], None]


def _log(fn: LogFn | None, msg: str) -> None:
    if fn:
        try:
            fn(msg)
        except Exception:
            pass


def kill_counter_enabled(cfg: dict[str, Any] | None) -> bool:
    """On by default; ``detect.kill_counter: false`` turns it off."""
    if cfg and isinstance(cfg.get("detect"), dict):
        val = cfg["detect"].get("kill_counter")
        if val is not None:
            return bool(val)
    return True


def resolve_tesseract(cfg: dict[str, Any] | None = None) -> str | None:
    """Locate a tesseract engine: config override, app bundle, PATH, common installs."""
    if cfg and isinstance(cfg.get("detect"), dict):
        raw = str(cfg["detect"].get("tesseract_path") or "").strip()
        if raw and Path(raw).is_file():
            raw_path = Path(raw)
            if (raw_path.parent / "tessdata").is_dir() or _tessdata_near(raw_path):
                return str(raw_path.resolve())
            return str(raw_path.resolve())
    exe = "tesseract.exe" if os.name == "nt" else "tesseract"
    for base in (app_dir(), resource_dir()):
        cand = base / "tesseract" / exe
        if cand.is_file():
            return str(cand.resolve())
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for root in (
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ):
            if not root:
                continue
            cand = Path(root) / "Tesseract-OCR" / "tesseract.exe"
            if cand.is_file():
                return str(cand.resolve())
    return None


def _tessdata_near(tesseract: Path) -> bool:
    return (tesseract.parent / "tessdata").is_dir()


def _tessdata_dir(tesseract: str) -> str | None:
    cand = Path(tesseract).parent / "tessdata"
    return str(cand) if cand.is_dir() else None


def resolve_counter_roi(cfg: dict[str, Any] | None) -> dict[str, float]:
    roi = dict(_DEFAULT_ROI)
    if cfg and isinstance(cfg.get("detect"), dict):
        raw = cfg["detect"].get("counter_roi")
        if isinstance(raw, dict):
            for key in ("x", "y", "w", "h"):
                if key in raw:
                    try:
                        roi[key] = float(raw[key])
                    except (TypeError, ValueError):
                        pass
    x = min(1.0, max(0.0, float(roi["x"])))
    y = min(1.0, max(0.0, float(roi["y"])))
    w = min(1.0 - x, max(0.005, float(roi["w"])))
    h = min(1.0 - y, max(0.005, float(roi["h"])))
    return {"x": x, "y": y, "w": w, "h": h}


def counter_sample_fps(cfg: dict[str, Any] | None) -> float:
    if cfg and isinstance(cfg.get("detect"), dict):
        try:
            fps = float(cfg["detect"].get("counter_sample_fps") or 0.5)
            return max(0.1, min(5.0, fps))
        except (TypeError, ValueError):
            pass
    return 0.5


def _probe_geometry(ffprobe: str | None, source: Path) -> tuple[int, int, float] | None:
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(source)],
            capture_output=True, text=True, timeout=30,
        )
        w = h = 0
        dur = 0.0
        for line in (out.stdout or "").splitlines():
            parts = [p for p in line.strip().split(",") if p]
            if len(parts) == 2 and parts[0].isdigit():
                w, h = int(parts[0]), int(parts[1])
            elif len(parts) == 1:
                try:
                    dur = float(parts[0])
                except ValueError:
                    pass
        if w > 0 and h > 0:
            return w, h, dur
    except Exception:
        pass
    return None


def _write_pgm(path: Path, w: int, h: int, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(b"P5\n%d %d\n255\n" % (w, h))
        fh.write(data)


def _cut_box(frame: bytes, fw: int, fh: int, box: tuple[int, int, int, int]) -> tuple[int, int, bytes]:
    x0, y0, bw, bh = box
    x0 = max(0, min(x0, fw - 1))
    y0 = max(0, min(y0, fh - 1))
    bw = max(1, min(bw, fw - x0))
    bh = max(1, min(bh, fh - y0))
    rows = []
    for r in range(y0, y0 + bh):
        rows.append(frame[r * fw + x0: r * fw + x0 + bw])
    return bw, bh, b"".join(rows)


def _ocr_digits(tesseract: str, tessdata: str | None, pgm: Path) -> int | None:
    cmd = [tesseract, str(pgm), "stdout", *_OCR_ARGS]
    if tessdata:
        cmd += ["--tessdata-dir", tessdata]
    env = None
    if tessdata:
        env = dict(os.environ)
        env["TESSDATA_PREFIX"] = tessdata
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    except Exception:
        return None
    digits = re.sub(r"\D", "", r.stdout or "")
    if not digits:
        return None
    try:
        v = int(digits)
    except ValueError:
        return None
    return v if 0 <= v <= 99 else None


def _read_pgm(path: Path) -> tuple[int, int, bytes] | None:
    try:
        raw = path.read_bytes()
        if not raw.startswith(b"P5"):
            return None
        # header: P5 <w> <h> <maxval>\n  (comments start with #)
        idx = 2
        vals = []
        while len(vals) < 3:
            while idx < len(raw) and raw[idx:idx + 1].isspace():
                idx += 1
            if idx < len(raw) and raw[idx:idx + 1] == b"#":
                idx = raw.index(b"\n", idx) + 1
                continue
            start = idx
            while idx < len(raw) and not raw[idx:idx + 1].isspace():
                idx += 1
            vals.append(int(raw[start:idx]))
        idx += 1  # single whitespace after maxval
        w, h, _max = vals
        return w, h, raw[idx: idx + w * h]
    except Exception:
        return None


def _load_icon_template() -> bytes | None:
    cand = resource_dir() / "subscript" / "data" / _TEMPLATE_NAME
    got = _read_pgm(cand)
    if not got:
        return None
    w, h, data = got
    if w != _TEMPLATE_SIZE or h != _TEMPLATE_SIZE or len(data) < w * h:
        return None
    return data[: w * h]


def _resize_gray_box_avg(data: bytes, w: int, h: int, tw: int, th: int) -> bytes:
    """Box-average resize to (tw, th) — pure python, good enough for icon NCC."""
    out = bytearray(tw * th)
    for ty in range(th):
        y0 = ty * h // th
        y1 = max(y0 + 1, (ty + 1) * h // th)
        for tx in range(tw):
            x0 = tx * w // tw
            x1 = max(x0 + 1, (tx + 1) * w // tw)
            acc = 0
            n = 0
            for y in range(y0, min(y1, h)):
                row = y * w
                for x in range(x0, min(x1, w)):
                    acc += data[row + x]
                    n += 1
            out[ty * tw + tx] = acc // max(1, n)
    return bytes(out)


def _ncc(a: bytes, b: bytes) -> float:
    n = len(a)
    if n == 0 or n != len(b):
        return 0.0
    sa = sum(a)
    sb = sum(b)
    ma = sa / n
    mb = sb / n
    num = 0.0
    da = 0.0
    db = 0.0
    for i in range(n):
        xa = a[i] - ma
        xb = b[i] - mb
        num += xa * xb
        da += xa * xa
        db += xb * xb
    if da <= 0.0 or db <= 0.0:
        return 0.0
    return num / ((da * db) ** 0.5)


def icon_present(icon_small: bytes, template: bytes) -> float:
    """Best NCC of the template over the (same-sized) icon patch, ±2px search."""
    ts = _TEMPLATE_SIZE
    if len(icon_small) != ts * ts:
        return 0.0
    best = 0.0
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            patch = bytearray(ts * ts)
            for y in range(ts):
                sy = y + dy
                if sy < 0 or sy >= ts:
                    continue
                row = y * ts
                srow = sy * ts
                for x in range(ts):
                    sx = x + dx
                    if 0 <= sx < ts:
                        patch[row + x] = icon_small[srow + sx]
            score = _ncc(template, bytes(patch))
            if score > best:
                best = score
    return best


def _smooth_series(
    series: list[tuple[float, int | None]], *, window: float = 4.0, min_hits: int = 2
) -> list[tuple[float, int | None]]:
    """Drop one-off misreads: a value only survives if it is read again nearby.

    Real counter values persist for seconds (until the next kill); OCR noise is
    sporadic. Requiring 2 agreeing reads within ±``window`` seconds removes the
    oscillating garbage that otherwise fakes increments.
    """
    reads = [(t, v) for t, v in series if v is not None]
    keep: set[float] = set()
    for i, (t, v) in enumerate(reads):
        hits = 0
        for j in range(max(0, i - 8), min(len(reads), i + 9)):
            t2, v2 = reads[j]
            if v2 == v and abs(t2 - t) <= window:
                hits += 1
                if hits >= min_hits:
                    keep.add(t)
                    break
    return [(t, v if t in keep else None) for t, v in series]


def _find_increments(series: list[tuple[float, int | None]]) -> list[dict[str, Any]]:
    """Confirmed increments of the counter = kills (port of the offline scan)."""
    kills: list[dict[str, Any]] = []
    last: int | None = None
    streak: int | None = None
    for t, v in series:
        if v is None:
            continue
        if last is None:
            last, streak = v, v
            continue
        if v > last:
            streak = v
        if streak is not None and streak > last and v >= streak:
            n_new = streak - last
            if 1 <= n_new <= 4:
                for _ in range(n_new):
                    kills.append({"t": round(t, 1), "count": streak})
            last = streak
        elif v < last - 2:
            last = v  # new match / counter reset
            streak = v
    dedup: list[dict[str, Any]] = []
    for k in kills:
        if not dedup or k["t"] - dedup[-1]["t"] > 3:
            dedup.append(k)
    return dedup


def detect_counter_kills(
    source: Path,
    *,
    cfg: dict[str, Any] | None = None,
    work_dir: Path | None = None,
    on_log: LogFn | None = None,
) -> dict[str, Any]:
    """Read the kill counter over the whole video; return kill timestamps.

    Never raises: any failure returns an empty list with a human note so the
    highlight pipeline falls back to loudness-only.
    """
    source = Path(source)
    empty = {"kills": [], "engine": False, "note": ""}
    if not source.is_file():
        empty["note"] = "source missing"
        return empty

    tesseract = resolve_tesseract(cfg)
    if not tesseract:
        empty["note"] = "No tesseract engine found (bundled copy missing); loudness-only."
        return empty
    tessdata = _tessdata_dir(tesseract)

    try:
        ffmpeg = find_ffmpeg()
    except Exception:
        ffmpeg = None
    if not ffmpeg:
        empty["note"] = "ffmpeg missing; loudness-only."
        return empty
    ffprobe = find_ffprobe(ffmpeg)

    geom = _probe_geometry(ffprobe, source)
    if not geom:
        empty["note"] = "Could not probe video size; loudness-only."
        return empty
    fw, fh, duration = geom
    if duration <= 0:
        duration = 1e9  # unknown; single segment, stop at EOF

    roi = resolve_counter_roi(cfg)
    cx = int(fw * roi["x"])
    cy = int(fh * roi["y"])
    cw = max(8, int(fw * roi["w"]))
    ch = max(8, int(fh * roi["h"]))
    cx = min(cx, fw - cw)
    cy = min(cy, fh - ch)
    sw, sh = cw * _SCALE, ch * _SCALE
    fps = counter_sample_fps(cfg)

    # Sub-boxes in the scaled crop.
    def sub_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        bx, by, bw, bh = box
        return (int(bx * sw), int(by * sh), max(1, int(bw * sw)), max(1, int(bh * sh)))

    digit_box = sub_box(_DIGIT_BOX)
    icon_box = sub_box(_ICON_BOX)

    template = _load_icon_template()

    # Segment long videos so several ffmpeg decoders run in parallel.
    cpu = os.cpu_count() or 4
    if duration >= 1e8:
        n_seg = 1  # unknown length: single pass to EOF
        seg_len = 0.0
    elif duration > 150:
        n_seg = min(8, max(2, cpu))
        seg_len = duration / n_seg
    else:
        n_seg = 1
        seg_len = duration

    vf = (
        "fps=%g,crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos,format=gray"
        % (fps, cw, ch, cx, cy, sw, sh)
    )

    own_tmp = work_dir is None
    tmp_root = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="killcounter_"))
    tmp_root.mkdir(parents=True, exist_ok=True)

    series: list[tuple[float, int | None]] = []
    icons: dict[float, bytes] = {}  # timestamp -> icon patch (28x28) for menu rejection
    frame_bytes = sw * sh
    lock = threading.Lock()
    pgm_seq = [0]

    def ocr_one(item: tuple[int, float, bytes]) -> tuple[int, float, int | None]:
        idx, t, digits = item
        with lock:
            pgm_seq[0] += 1
            pgm = tmp_root / ("c_%06d.pgm" % pgm_seq[0])
        try:
            _write_pgm(pgm, digit_box[2], digit_box[3], digits)
            val = _ocr_digits(tesseract, tessdata, pgm)
        finally:
            try:
                pgm.unlink()
            except OSError:
                pass
        return idx, t, val

    def run_segment(seg: int, pool: ThreadPoolExecutor) -> None:
        start = seg * seg_len
        cmd = [
            ffmpeg, "-hide_banner", "-nostats", "-v", "error",
            "-ss", "%.3f" % start, "-i", str(source),
        ]
        if duration < 1e8:
            cmd += ["-t", "%.3f" % (seg_len + 1.0)]
        cmd += ["-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as exc:
            _log(on_log, "kill-counter: ffmpeg start failed (%s)" % exc)
            return
        assert proc.stdout is not None
        k = 0
        pending = []
        try:
            while True:
                buf = proc.stdout.read(frame_bytes)
                if not buf or len(buf) < frame_bytes:
                    break
                t = start + k / fps
                _dw, _dh, digits = _cut_box(buf, sw, sh, digit_box)
                iw, ih, icon_raw = _cut_box(buf, sw, sh, icon_box)
                with lock:
                    idx = len(series)
                    series.append((t, None))
                if template is not None:
                    icons[round(t, 3)] = _resize_gray_box_avg(
                        icon_raw, iw, ih, _TEMPLATE_SIZE, _TEMPLATE_SIZE
                    )
                pending.append((idx, t, digits))
                if len(pending) >= 16:
                    for i2, t2, val in pool.map(ocr_one, pending):
                        series[i2] = (t2, val)
                    pending = []
                k += 1
            if pending:
                for i2, t2, val in pool.map(ocr_one, pending):
                    series[i2] = (t2, val)
        except Exception as exc:
            _log(on_log, "kill-counter: decode stopped (%s)" % exc)
        finally:
            try:
                proc.stdout.close()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            threads = []
            for seg in range(n_seg):
                th = threading.Thread(target=run_segment, args=(seg, pool), daemon=True)
                th.start()
                threads.append(th)
            for th in threads:
                th.join()

        series.sort(key=lambda item: item[0])
        read_ok = sum(1 for _t, v in series if v is not None)
        if not series or read_ok == 0:
            empty["engine"] = True
            empty["note"] = "Kill counter unreadable (no numbers recognized); loudness-only."
            return empty

        # Only trust reads taken while the skull icon is actually on screen.
        # Spectating / gulag / menus show a different number in the same spot
        # (players-remaining countdown) whose noise otherwise fakes kills.
        if template is not None:
            in_game = 0
            filtered = []
            for t, v in series:
                patch = icons.get(round(t, 3))
                if patch is not None and _ncc(template, patch) >= _ICON_NCC_MIN:
                    in_game += 1
                    filtered.append((t, v))
                else:
                    filtered.append((t, None))
            series = filtered
            _log(on_log, "kill-counter: %d/%d frames in-game" % (in_game, len(series)))

        candidates = _find_increments(_smooth_series(series))
        if template is not None:
            for cand in candidates:
                t = float(cand["t"])
                best = 0.0
                for t2, patch in icons.items():
                    if abs(t2 - t) > 6.0:
                        continue
                    s = _ncc(template, patch)
                    if s > best:
                        best = s
                cand["icon"] = round(best, 3)

        note = "Kill counter: %d frame(s), %d read, %d kill(s)." % (len(series), read_ok, len(candidates))
        return {"kills": candidates, "engine": True, "note": note}
    except Exception as exc:  # noqa: BLE001 — fail-soft by contract
        empty["engine"] = True
        empty["note"] = "Kill-counter scan failed (%s); loudness-only." % exc
        return empty
    finally:
        if own_tmp:
            shutil.rmtree(tmp_root, ignore_errors=True)
