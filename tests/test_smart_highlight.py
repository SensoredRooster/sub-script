from pathlib import Path

from subscript.live_ui import make_profile_file_handler, smart_highlight_window


def test_smart_highlight_adds_context(monkeypatch, tmp_path: Path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(
        "subscript.live_ui.suggest_highlights_or_fallback",
        lambda *args, **kwargs: {
            "suggestions": [{"start": 10.0, "duration": 12.0, "score": 0.8}],
            "fallback": False,
            "message": "",
        },
    )
    profile = {
        "buffer_seconds": 12,
        "smart_pre_roll": 3,
        "smart_post_roll": 2,
    }
    start, duration, note = smart_highlight_window(source, {}, profile)
    assert start == 7.0
    assert duration == 17.0
    assert "confidence 80%" in note


def test_smart_highlight_fail_soft_uses_tail_window(monkeypatch, tmp_path: Path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(
        "subscript.live_ui.suggest_highlights_or_fallback",
        lambda *args, **kwargs: {
            "suggestions": [{"start": None, "duration": 15.0, "score": 0.0}],
            "fallback": True,
            "message": "analysis unavailable",
        },
    )
    profile = {
        "buffer_seconds": 15,
        "smart_pre_roll": 3,
        "smart_post_roll": 2,
    }
    start, duration, note = smart_highlight_window(source, {}, profile)
    assert start is None
    assert duration == 20.0
    assert note == "analysis unavailable"


def test_profile_handler_passes_smart_window_to_pipeline(monkeypatch, tmp_path: Path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    calls = []
    monkeypatch.setattr(
        "subscript.live_ui.smart_highlight_window",
        lambda *args, **kwargs: (5.0, 19.0, "ok"),
    )
    monkeypatch.setattr(
        "subscript.live_ui.run_pipeline",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    profile = {
        "folder": str(tmp_path),
        "source_mode": "smart_highlight",
        "buffer_seconds": 14,
        "review_mode": "review",
        "platforms": {},
    }
    handler = make_profile_file_handler({}, profile)
    handler(source)
    assert calls[0][1]["start"] == 5.0
    assert calls[0][1]["duration"] == 19.0
    assert calls[0][1]["dry_run"] is True
