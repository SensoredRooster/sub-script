"""Kill-counter detection: pure-logic units (no ffmpeg/tesseract needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from subscript import kill_counter as KC


def test_enabled_default_and_override() -> None:
    assert KC.kill_counter_enabled(None) is True
    assert KC.kill_counter_enabled({}) is True
    assert KC.kill_counter_enabled({"detect": {"kill_counter": False}}) is False
    assert KC.kill_counter_enabled({"detect": {"kill_counter": True}}) is True


def test_resolve_counter_roi_defaults_and_clamp() -> None:
    roi = KC.resolve_counter_roi(None)
    assert 0.9 < roi["x"] < 1.0 and 0.0 < roi["y"] < 0.1
    assert roi["x"] + roi["w"] <= 1.0 and roi["y"] + roi["h"] <= 1.0
    bad = KC.resolve_counter_roi({"detect": {"counter_roi": {"x": 5, "y": -2, "w": 9, "h": 0}}})
    assert bad["x"] == 1.0 - bad["w"] or bad["x"] + bad["w"] <= 1.0
    assert bad["y"] == 0.0
    assert bad["w"] <= 1.0 and bad["h"] >= 0.005


def test_sample_fps_default_and_clamp() -> None:
    assert KC.counter_sample_fps(None) == pytest.approx(0.5)
    assert KC.counter_sample_fps({"detect": {"counter_sample_fps": 99}}) == 5.0
    assert KC.counter_sample_fps({"detect": {"counter_sample_fps": "junk"}}) == pytest.approx(0.5)


def test_pgm_roundtrip(tmp_path: Path) -> None:
    data = bytes(range(256))[: 16 * 12]
    p = tmp_path / "x.pgm"
    KC._write_pgm(p, 16, 12, data)
    got = KC._read_pgm(p)
    assert got is not None
    w, h, raw = got
    assert (w, h) == (16, 12)
    assert raw == data
    assert KC._read_pgm(tmp_path / "missing.pgm") is None


def test_ncc_properties() -> None:
    a = bytes([10, 200, 30, 250, 90])
    assert KC._ncc(a, a) == pytest.approx(1.0)
    inv = bytes([250 - v for v in a])
    assert KC._ncc(a, inv) == pytest.approx(-1.0)
    assert KC._ncc(a, bytes([7] * 5)) == 0.0  # constant patch: no variance
    assert KC._ncc(a, b"") == 0.0


def test_resize_box_avg_uniform_and_gradient() -> None:
    uniform = bytes([100] * (8 * 8))
    out = KC._resize_gray_box_avg(uniform, 8, 8, 4, 4)
    assert out == bytes([100] * 16)
    # 8x8 gradient: each 2x2 block averages to its mean
    grad = bytes((x * 20) % 256 for y in range(8) for x in range(8))
    out2 = KC._resize_gray_box_avg(grad, 8, 8, 4, 4)
    assert len(out2) == 16
    assert out2[0] == (0 + 20 + 0 + 20) // 4  # block over x=0,1


def test_icon_present_self_match() -> None:
    # A template matched against itself (embedded in a same-size patch) is 1.0.
    tmpl = bytes((x * y) % 256 for y in range(28) for x in range(28))
    assert KC.icon_present(tmpl, tmpl) == pytest.approx(1.0)
    assert KC.icon_present(bytes(28 * 28), tmpl) == 0.0  # black patch: no icon


def test_bundled_icon_template_integrity() -> None:
    # The skull template ships base64-embedded so line endings can't corrupt it.
    tmpl = KC._load_icon_template()
    assert tmpl is not None and len(tmpl) == 28 * 28
    assert len(set(tmpl)) > 8  # real image data, not a constant
    assert KC.icon_present(tmpl, tmpl) == pytest.approx(1.0)


def test_find_increments_basic_and_reset() -> None:
    series = [
        (0.0, 2), (2.0, 2), (4.0, 3), (6.0, 3),   # kill at 4
        (10.0, 0), (12.0, 0),                      # drop > 2: new match reset
        (14.0, 2), (16.0, 2),                      # +2 jump: kills at 14
    ]
    kills = KC._find_increments(series)
    assert [k["t"] for k in kills] == [4.0, 14.0]
    assert kills[0]["count"] == 3 and kills[1]["count"] == 2


def test_find_increments_spike_fires_raw_but_smoothing_catches_it() -> None:
    # Raw logic fires on an instant jump (confirmation happens upstream in
    # _smooth_series); this pins the raw behaviour so the pair stays coherent.
    series = [(0.0, 3), (2.0, 3), (4.0, 7), (6.0, 3), (8.0, 3)]
    assert [k["t"] for k in KC._find_increments(series)] == [4.0]
    assert KC._find_increments(KC._smooth_series(series)) == []


def test_find_increments_caps_multikill_and_dedupes() -> None:
    series = [(0.0, 0), (2.0, 9), (4.0, 9)]  # +9 jump: implausible, ignored
    assert KC._find_increments(series) == []
    series2 = [(0.0, 0), (2.0, 2), (4.0, 2)]  # +2 jump: two kills, same timestamp
    kills = KC._find_increments(series2)
    assert len(kills) == 1  # dedup collapses same-instant double kill entries
    assert kills[0]["count"] == 2


def test_smooth_series_drops_one_off_misreads() -> None:
    series = [
        (0.0, 5), (2.0, 5), (4.0, 35), (6.0, 5), (8.0, 5),
        (10.0, 6), (12.0, 6),
    ]
    smoothed = KC._smooth_series(series)
    assert [v for _t, v in smoothed] == [5, 5, None, 5, 5, 6, 6]
    kills = KC._find_increments(smoothed)
    assert [k["t"] for k in kills] == [10.0]


def test_smooth_series_keeps_sparse_but_repeated_reads() -> None:
    series = [(0.0, None), (1.0, 4), (2.0, None), (3.0, 4), (4.0, None)]
    smoothed = KC._smooth_series(series)
    assert [v for _t, v in smoothed] == [None, 4, None, 4, None]


def test_detect_counter_kills_fail_soft(tmp_path: Path) -> None:
    res = KC.detect_counter_kills(tmp_path / "nope.mp4", cfg=None)
    assert res["kills"] == [] and res["engine"] is False
    assert "source missing" in res["note"]


def test_resolve_tesseract_cfg_override(tmp_path: Path) -> None:
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"MZ")
    got = KC.resolve_tesseract({"detect": {"tesseract_path": str(fake)}})
    assert got == str(fake.resolve())
    assert KC.resolve_tesseract({"detect": {"tesseract_path": str(tmp_path / "nope.exe")}}) != str(tmp_path / "nope.exe")


def test_merge_prefers_killcounter_source() -> None:
    from subscript.detect_killfeed import merge_highlight_suggestions

    loud = [{"start": 0.0, "duration": 30.0, "score": 1.0, "source": "loudness"}]
    kills = [{"start": 5.0, "duration": 30.0, "score": 1.0, "source": "killcounter"}]
    merged = merge_highlight_suggestions(loud, kills, top_n=5, mode="merge")
    assert merged[0]["source"] == "killcounter"
    assert all(s["source"] != "loudness" or s["start"] != 0.0 for s in merged)
