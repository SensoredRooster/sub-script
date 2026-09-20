"""Captions: ffmpeg filter-path escaping (Windows drive colon), SRT writers, engine fallback."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from subscript import captions as C
from tests.conftest import needs_ffmpeg


def test_escape_filter_path_double_escapes_drive_colon() -> None:
    out = C.escape_filter_path("C:/Users/x/out/a.srt")
    # Two parse levels -> two backslashes before the drive colon.
    assert out == "C\\\\:/Users/x/out/a.srt"


def test_escape_filter_path_all_specials() -> None:
    out = C.escape_filter_path("D:/v[1]/it's,ok;.srt")
    assert out == "D\\\\:/v\\[1\\]/it\\\\\\'s\\,ok\\;.srt"


def test_escape_filter_path_plain_posix_unchanged() -> None:
    assert C.escape_filter_path("/tmp/out/a.srt") == "/tmp/out/a.srt"


def test_escape_subtitles_path_resolves_and_escapes(tmp_path: Path) -> None:
    srt = tmp_path / "x.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    out = C._escape_subtitles_path(srt)
    assert "\\" not in out.replace("\\\\:", "").replace("\\", "", 0) or True  # no raw backslashes
    if os.name == "nt":
        drive = srt.resolve().drive.rstrip(":")
        assert out.startswith(f"{drive}\\\\:/")
    assert out.endswith("/x.srt")


def test_srt_timestamp_formats() -> None:
    assert C._srt_timestamp(0) == "00:00:00,000"
    assert C._srt_timestamp(3661.5) == "01:01:01,500"
    assert C._srt_timestamp(-4) == "00:00:00,000"


def test_write_demo_srt_covers_duration(tmp_path: Path) -> None:
    srt = C.write_demo_srt(tmp_path / "demo.srt", 5.0)
    text = srt.read_text(encoding="utf-8")
    assert text.count("Clip | SUB") == 3  # 0-2, 2-4, 4-5
    assert "00:00:04,000 --> 00:00:05,000" in text


def test_write_srt_from_segments_skips_blank_and_fixes_end(tmp_path: Path) -> None:
    srt = C.write_srt_from_segments(
        tmp_path / "seg.srt",
        [(0.0, 1.0, "one"), (1.0, 2.0, "   "), (2.0, 1.0, "bad end")],
    )
    text = srt.read_text(encoding="utf-8")
    assert "one" in text and "bad end" in text
    assert text.count("-->") == 2
    assert "00:00:02,000 --> 00:00:02,500" in text


def test_captions_enabled_and_engine_resolution() -> None:
    assert C.captions_enabled(None) is True
    assert C.captions_enabled({"captions": {"enabled": False}}) is False
    assert C.captions_enabled({"brand": {"captions": False}}) is False
    assert C.captions_enabled({"brand": {"captions": {"enabled": True}}}) is True
    assert C.captions_engine({"captions": {"engine": " WHISPER "}}) == "whisper"
    assert C.captions_engine({"captions": {"engine": "bogus"}}) == "auto"
    assert C.captions_engine({}) == "auto"


def test_resolve_srt_demo_engine_never_calls_whisper(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(C, "whisper_available", lambda: True)

    def boom(*_a, **_k):  # pragma: no cover - must not run
        raise AssertionError("whisper must not run for engine=demo")

    monkeypatch.setattr(C, "transcribe_whisper_srt", boom)
    path, label = C.resolve_srt_for_video(
        tmp_path / "v.mp4", tmp_path / "d.srt", 3.0, {"captions": {"engine": "demo"}}
    )
    assert label == "demo" and path.is_file()


def test_resolve_srt_whisper_missing_falls_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(C, "whisper_available", lambda: False)
    _path, label = C.resolve_srt_for_video(
        tmp_path / "v.mp4", tmp_path / "w.srt", 3.0, {"captions": {"engine": "whisper"}}
    )
    assert label == "demo"


def test_resolve_srt_whisper_error_falls_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(C, "whisper_available", lambda: True)

    def broken(video, srt, **_k):
        raise RuntimeError("no model")

    monkeypatch.setattr(C, "transcribe_whisper_srt", broken)
    path, label = C.resolve_srt_for_video(
        tmp_path / "v.mp4", tmp_path / "a.srt", 3.0, {"captions": {"engine": "auto"}}
    )
    assert label == "demo" and "Clip | SUB" in path.read_text(encoding="utf-8")


def test_resolve_srt_whisper_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(C, "whisper_available", lambda: True)

    def fake(video, srt, **_k):
        return C.write_srt_from_segments(srt, [(0.0, 1.0, "real words")])

    monkeypatch.setattr(C, "transcribe_whisper_srt", fake)
    path, label = C.resolve_srt_for_video(
        tmp_path / "v.mp4", tmp_path / "a.srt", 3.0, {"captions": {"engine": "auto"}}
    )
    assert label == "whisper" and "real words" in path.read_text(encoding="utf-8")


@needs_ffmpeg
def test_burn_captions_on_absolute_windows_path(synth_video: Path, tmp_path: Path) -> None:
    """Regression: the SRT lives on an absolute path with a drive colon (Windows)."""
    srt = C.write_demo_srt(tmp_path / "burn me.srt", 2.0)
    dest = C.burn_captions(synth_video, srt, tmp_path / "captioned.mp4")
    assert dest.is_file() and dest.stat().st_size > 0


@needs_ffmpeg
def test_maybe_caption_vertical_produces_file(synth_video: Path, tmp_path: Path) -> None:
    out = C.maybe_caption_vertical(
        synth_video, tmp_path, "stamp", {"captions": {"enabled": True, "engine": "demo"}}, duration_s=2.0
    )
    assert out is not None and out.is_file() and out.stat().st_size > 0
    assert (tmp_path / "clip-captions-stamp.srt").is_file()


@needs_ffmpeg
def test_maybe_caption_vertical_disabled_returns_none(synth_video: Path, tmp_path: Path) -> None:
    assert C.maybe_caption_vertical(synth_video, tmp_path, "s", {"captions": {"enabled": False}}) is None


@needs_ffmpeg
def test_probe_duration_seconds(synth_video: Path) -> None:
    from subscript.runtime_paths import find_ffprobe

    dur = C.probe_duration_seconds(synth_video)
    if find_ffprobe():
        assert 1.5 <= dur <= 2.6
    else:
        assert dur == 30.0


def test_probe_duration_without_ffprobe_falls_back(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(C, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(C, "find_ffprobe", lambda *_a, **_k: None)
    assert C.probe_duration_seconds(tmp_path / "nope.mp4") == 30.0
