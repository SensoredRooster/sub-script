"""Burn SRT captions onto video; optional faster-whisper STT with demo fallback."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from subscript.clip import (
    COMPAT_AUDIO,
    COMPAT_MOVFLAGS,
    COMPAT_VIDEO,
    require_ffmpeg,
    run_ffmpeg,
)
from subscript.runtime_paths import find_ffprobe

_DEMO_LINE = "Clip | SUB"
_VALID_ENGINES = frozenset({"auto", "demo", "whisper"})


def captions_enabled(cfg: dict[str, Any] | None) -> bool:
    """True unless captions.enabled is explicitly false (brand or top-level)."""
    if not cfg:
        return True
    caps = cfg.get("captions")
    if isinstance(caps, dict) and "enabled" in caps:
        return bool(caps["enabled"])
    brand = cfg.get("brand") or {}
    if isinstance(brand, dict) and "captions" in brand:
        nested = brand["captions"]
        if isinstance(nested, dict) and "enabled" in nested:
            return bool(nested["enabled"])
        if isinstance(nested, bool):
            return nested
    return True


def captions_engine(cfg: dict[str, Any] | None) -> str:
    """Return captions.engine: auto | demo | whisper (default auto)."""
    if not cfg:
        return "auto"
    caps = cfg.get("captions")
    if isinstance(caps, dict):
        raw = str(caps.get("engine") or "auto").strip().lower()
        if raw in _VALID_ENGINES:
            return raw
    return "auto"


def whisper_available() -> bool:
    """True if faster-whisper can be imported (optional extra)."""
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_demo_srt(
    path: Path,
    duration_s: float,
    *,
    text: str = _DEMO_LINE,
    segment_s: float = 2.0,
) -> Path:
    """Write simple timed placeholder captions covering ``duration_s``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, float(duration_s))
    seg = max(0.5, float(segment_s))
    blocks: list[str] = []
    idx = 1
    t = 0.0
    while t < duration - 0.05:
        end = min(t + seg, duration)
        blocks.append(
            f"{idx}\n{_srt_timestamp(t)} --> {_srt_timestamp(end)}\n{text}\n"
        )
        idx += 1
        t = end
    if not blocks:
        blocks.append(
            f"1\n{_srt_timestamp(0)} --> {_srt_timestamp(duration)}\n{text}\n"
        )
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return path


def write_srt_from_segments(
    path: Path,
    segments: list[tuple[float, float, str]],
) -> Path:
    """Write SRT from (start, end, text) segments."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    idx = 1
    for start, end, text in segments:
        line = (text or "").strip()
        if not line:
            continue
        if end <= start:
            end = start + 0.5
        blocks.append(
            f"{idx}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{line}\n"
        )
        idx += 1
    if not blocks:
        path.write_text("", encoding="utf-8")
        return path
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return path


def _extract_audio_wav(video: Path, wav: Path) -> Path:
    """Decode mono 16 kHz WAV for STT (fail raises)."""
    ffmpeg = require_ffmpeg()
    wav = Path(wav)
    wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not wav.is_file() or wav.stat().st_size == 0:
        err = (proc.stderr or proc.stdout or "").strip()
        tail = "\n".join(err.splitlines()[-15:]) if err else "(no ffmpeg output)"
        raise RuntimeError(f"audio extract for whisper failed:\n{tail}")
    return wav


def transcribe_whisper_srt(
    video: Path,
    srt: Path,
    *,
    model_size: str = "base",
) -> Path:
    """Run faster-whisper on ``video`` audio and write timed SRT.

    Raises if faster-whisper is missing or transcription fails.
    """
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

    video = Path(video)
    srt = Path(srt)
    wav = srt.with_suffix(".wav")
    try:
        _extract_audio_wav(video, wav)
        # CPU int8 keeps optional install usable on Windows without CUDA.
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments_iter, _info = model.transcribe(str(wav), vad_filter=True)
        segs: list[tuple[float, float, str]] = []
        for seg in segments_iter:
            segs.append((float(seg.start), float(seg.end), str(seg.text or "")))
        if not segs:
            raise RuntimeError("whisper returned no segments")
        return write_srt_from_segments(srt, segs)
    finally:
        try:
            wav.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_srt_for_video(
    video: Path,
    srt: Path,
    duration_s: float,
    cfg: dict[str, Any],
) -> tuple[Path, str]:
    """Pick SRT source from captions.engine; always fail-soft to demo.

    Returns ``(srt_path, source_label)`` where source_label is
    ``whisper`` or ``demo``.
    """
    engine = captions_engine(cfg)
    want_whisper = engine in ("auto", "whisper")
    if want_whisper and whisper_available():
        try:
            transcribe_whisper_srt(video, srt)
            if srt.is_file() and srt.stat().st_size > 0:
                return srt, "whisper"
        except Exception as exc:  # noqa: BLE001
            print(f"Whisper captions failed ({exc}); using demo SRT.")
    elif engine == "whisper" and not whisper_available():
        print(
            "captions.engine=whisper but faster-whisper is not installed; "
            "using demo SRT. Optional: pip install -r requirements-whisper.txt"
        )
    write_demo_srt(srt, duration_s)
    return srt, "demo"


def _ff_escape(text: str, specials: str) -> str:
    """Backslash-escape ``specials`` (plus the backslash itself) for one ffmpeg parse level."""
    out: list[str] = []
    for ch in text:
        if ch == "\\" or ch in specials:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def escape_filter_path(posix_path: str) -> str:
    """Escape a file path for use inside an ffmpeg filter option (e.g. ``subtitles=``).

    ffmpeg parses a ``-vf`` string twice: the filtergraph parser first (where
    ``[ ] , ; '`` and backslash are special), then the per-filter option parser
    (where ``:`` ``'`` and backslash are special). A Windows drive colon therefore
    needs *two* levels of escaping: ``C:/x.srt`` must become ``C\\\\:/x.srt``.
    Escaping only once made ffmpeg split the path at the drive colon and fail with
    ``Unable to parse "original_size"`` on every Windows machine.
    """
    s = _ff_escape(posix_path, ":'")  # option-parser level
    s = _ff_escape(s, "[],;'")  # filtergraph-parser level
    return s


def _escape_subtitles_path(path: Path) -> str:
    """Escape an absolute path for the ffmpeg ``subtitles=`` filter (Windows-safe)."""
    return escape_filter_path(Path(path).resolve().as_posix())


def _run_ffmpeg(cmd: list[str]) -> None:
    run_ffmpeg(cmd, what="ffmpeg captions")


def burn_captions(video: Path, srt: Path, dest: Path) -> Path:
    """Burn ``srt`` onto ``video`` via ffmpeg subtitles filter -> ``dest``."""
    ffmpeg = require_ffmpeg()
    video = Path(video)
    srt = Path(srt)
    dest = Path(dest)
    if not video.exists():
        raise FileNotFoundError(f"video not found: {video}")
    if not srt.exists():
        raise FileNotFoundError(f"srt not found: {srt}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    sub_path = _escape_subtitles_path(srt)
    style = (
        "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=80"
    )
    vf = f"subtitles={sub_path}:force_style='{style}'"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vf",
        vf,
        *COMPAT_VIDEO,
        *COMPAT_AUDIO,
        *COMPAT_MOVFLAGS,
        str(dest),
    ]
    try:
        _run_ffmpeg(cmd)
        return dest
    except RuntimeError:
        vf_plain = f"subtitles={sub_path}"
        cmd_plain = [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-vf",
            vf_plain,
            *COMPAT_VIDEO,
            *COMPAT_AUDIO,
            *COMPAT_MOVFLAGS,
            str(dest),
        ]
        _run_ffmpeg(cmd_plain)
        return dest


def probe_duration_seconds(video: Path) -> float:
    """Best-effort duration via ffprobe; falls back to 30s."""
    ffprobe = find_ffprobe(require_ffmpeg())
    if not ffprobe:
        return 30.0
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            val = float((proc.stdout or "").strip())
            if val > 0:
                return val
    except Exception:
        pass
    return 30.0


def maybe_caption_vertical(
    vertical: Path,
    out_dir: Path,
    stamp: str,
    cfg: dict[str, Any],
    *,
    duration_s: float | None = None,
) -> Path | None:
    """If captions enabled, resolve SRT (whisper or demo) and burn onto vertical."""
    if not captions_enabled(cfg):
        return None
    vertical = Path(vertical)
    if not vertical.exists():
        return None
    dur = float(duration_s) if duration_s is not None else probe_duration_seconds(vertical)
    srt = out_dir / f"clip-captions-{stamp}.srt"
    try:
        resolve_srt_for_video(vertical, srt, dur, cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"Caption SRT skipped: {exc}")
        try:
            write_demo_srt(srt, dur)
        except Exception:
            return None
    dest = out_dir / f"clip-vertical-captioned-{stamp}.mp4"
    try:
        return burn_captions(vertical, srt, dest)
    except RuntimeError as exc:
        print(f"Caption burn skipped: {exc}")
        return None


def maybe_caption_horizontal(horizontal: Path, out_dir: Path, stamp: str, cfg: dict[str, Any]) -> Path:
    """Use the same timed captions for landscape; retain plain video on failure."""
    srt = out_dir / f"clip-captions-{stamp}.srt"
    if not captions_enabled(cfg) or not srt.is_file():
        return horizontal
    dest = out_dir / f"clip-horizontal-captioned-{stamp}.mp4"
    try:
        return burn_captions(horizontal, srt, dest)
    except RuntimeError:
        return horizontal
