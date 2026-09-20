"""Loudness highlights + experimental kill-feed helpers (pure logic; ffmpeg parts marked)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from subscript import detect_killfeed as K
from subscript import highlights as H
from tests.conftest import FFMPEG, needs_ffmpeg


def test_rms() -> None:
    assert H._rms([]) == 0.0
    assert H._rms([0.5, -0.5]) == pytest.approx(0.5)


def test_fallback_payload_for_missing_source(tmp_path: Path) -> None:
    payload = H.suggest_highlights_or_fallback(tmp_path / "nope.mp4", buffer_seconds=30.0, top_n=3)
    assert payload["fallback"] is True
    assert payload["suggestions"][0]["start"] is None
    assert payload["suggestions"][0]["duration"] == 30.0
    assert "last 30 seconds" in payload["message"]


def test_suggest_highlights_rejects_bad_buffer(tmp_path: Path) -> None:
    src = tmp_path / "x.mp4"
    src.write_bytes(b"not a video")
    with pytest.raises(ValueError):
        H.suggest_highlights(src, buffer_seconds=0)


def test_merge_suggestions_prefers_killfeed_and_dedupes_overlap() -> None:
    loud = [
        {"start": 0.0, "duration": 30.0, "score": 0.9, "source": "loudness"},
        {"start": 100.0, "duration": 30.0, "score": 0.4, "source": "loudness"},
    ]
    kills = [{"start": 10.0, "duration": 30.0, "score": 1.0, "source": "killfeed"}]
    merged = K.merge_highlight_suggestions(loud, kills, top_n=5, mode="merge")
    starts = [s["start"] for s in merged]
    assert starts == [10.0, 100.0]  # overlapping loud window at 0 dropped, sorted by start
    assert merged[0]["source"] == "killfeed"

    replaced = K.merge_highlight_suggestions(loud, kills, top_n=5, mode="replace")
    assert [s["start"] for s in replaced] == [10.0]

    # replace with no kill hits keeps loudness
    kept = K.merge_highlight_suggestions(loud, [], top_n=1, mode="replace")
    assert len(kept) == 1 and kept[0]["start"] == 0.0


def test_kills_to_suggestions_pre_roll_clamps_at_zero() -> None:
    out = K.kills_to_suggestions([{"t": 3.0}, {"t": 50.0}], buffer_seconds=20.0, pre_roll=8.0)
    assert out[0]["start"] == 0.0 and out[1]["start"] == 42.0
    assert all(s["duration"] == 20.0 and s["source"] == "killfeed" for s in out)


def test_player_name_exact_match_only() -> None:
    assert K.player_name_in_text("SensoredRooster killed Foo", "SensoredRooster")
    assert K.player_name_in_text("sensoredrooster  killed Foo", "SensoredRooster")
    assert not K.player_name_in_text("SensoredRoosterX killed Foo", "SensoredRooster")
    assert not K.player_name_in_text("Enemy killed Foo", "SensoredRooster")
    assert not K.player_name_in_text("anything", "")
    assert K.player_name_in_text("[TAG]Roo.ster killed", "Roo.ster")  # regex specials escaped


def test_roi_and_stream_helpers() -> None:
    roi = K.resolve_roi({"detect": {"roi": {"x": 0.9, "y": -1, "w": 0.5, "h": 2}}})
    assert roi["x"] == 0.9 and roi["y"] == 0.0
    assert roi["w"] == pytest.approx(0.1) and roi["h"] == 1.0
    assert K.resolve_roi(None) == K._DEFAULT_ROI
    assert K.resolve_stream_size({"stream": {"resolution": "1920x1080"}}) == (1920, 1080)
    assert K.resolve_stream_size({"stream": {"resolution": "2560 X 1440"}}) == (2560, 1440)
    assert K.resolve_stream_size({"stream": {"resolution": "big"}}) is None
    assert K.resolve_stream_size(None) is None
    x, y, w, h = K.roi_pixel_box(1920, 1080, K._DEFAULT_ROI)
    assert x + w <= 1920 and y + h <= 1080 and w > 0 and h > 0
    assert K.sample_fps({"detect": {"sample_fps": 99}}) == 10.0
    assert K.sample_fps({"detect": {"sample_fps": "x"}}) == 1.0


def test_detect_flags_and_player_name_fallback() -> None:
    assert K.detect_enabled(None) is False
    assert K.detect_enabled({"detect": {"enabled": True}}) is True
    assert K.resolve_player_name({"stream": {"player_name": "Streamer"}}) == "Streamer"
    assert K.resolve_player_name({"detect": {"player_name": "Exact"}, "stream": {"player_name": "x"}}) == "Exact"


def test_detect_kills_without_name_or_ocr(tmp_path: Path) -> None:
    result = K.detect_kills(tmp_path / "v.mp4", player_name="")
    assert result["kills"] == [] and "empty" in result["note"]
    if not K.ocr_available():
        result = K.detect_kills(tmp_path / "v.mp4", player_name="Me")
        assert result["kills"] == [] and "OCR engine not installed" in result["note"]


def test_merge_killfeed_skipped_when_disabled() -> None:
    loud = [{"start": 0.0, "duration": 5.0, "score": 1.0, "source": "loudness"}]
    out, note = H._maybe_merge_killfeed(Path("x.mp4"), loud, buffer_seconds=5.0, top_n=3, cfg={"detect": {"enabled": False}})
    assert out == loud and note == ""
    out, note = H._maybe_merge_killfeed(Path("x.mp4"), loud, buffer_seconds=5.0, top_n=3, cfg={"detect": {"enabled": True}})
    assert out == loud and "player_name empty" in note


@needs_ffmpeg
def test_suggest_highlights_finds_loud_middle(tmp_path: Path) -> None:
    src = tmp_path / "quiet_loud_quiet.mp4"
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=160x120:r=10:d=6",
        "-f", "lavfi", "-i", "aevalsrc=0.02*sin(2*PI*440*t):s=8000:d=2",
        "-f", "lavfi", "-i", "aevalsrc=0.9*sin(2*PI*440*t):s=8000:d=2",
        "-f", "lavfi", "-i", "aevalsrc=0.02*sin(2*PI*440*t):s=8000:d=2",
        "-filter_complex", "[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(src),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    suggestions = H.suggest_highlights(src, buffer_seconds=2.0, top_n=3)
    best = max(suggestions, key=lambda s: s["score"])
    mid = best["start"] + best["duration"] / 2
    assert 1.5 <= mid <= 4.5, suggestions
    assert best["score"] == 1.0
    starts = [s["start"] for s in suggestions]
    assert starts == sorted(starts)

    payload = H.suggest_highlights_or_fallback(src, buffer_seconds=2.0, top_n=2, cfg={"detect": {"enabled": False}})
    assert payload["fallback"] is False and len(payload["suggestions"]) == 2
    assert all(s["source"] == "loudness" for s in payload["suggestions"])
