from pathlib import Path
from subscript.publish import PublishMeta, PublishResult
from subscript.publish.orchestrator import run_enabled_publishers
from subscript.post_metadata import generate_posts
from subscript.captions import maybe_caption_horizontal


def test_youtube_landscape_routes_correct_file_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    horizontal = tmp_path / "horizontal.mp4"
    horizontal.write_bytes(b"landscape")
    vertical = tmp_path / "vertical.mp4"
    vertical.write_bytes(b"vertical")
    calls = []
    monkeypatch.setattr("subscript.publish.youtube.upload_youtube", lambda path, cfg: calls.append((path, cfg)) or {"url": "https://youtu.be/test"})
    cfg = {"youtube": {"enabled": True}, "platforms": {"youtube": {"format": "horizontal"}}}
    meta = PublishMeta("test", "Test", tmp_path, tmp_path, extra={"post_metadata": generate_posts({})})
    results = run_enabled_publishers(vertical, meta, cfg, tmp_path)
    assert results[0].status == "uploaded"
    assert calls[0][0] == horizontal
    assert calls[0][1]["format"] == "horizontal"
    assert "#Shorts" not in calls[0][1]["description"]


def test_missing_landscape_does_not_silently_upload_vertical(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("subscript.publish.youtube.upload_youtube", lambda *a: calls.append(a))
    cfg = {"youtube": {"enabled": True}, "platforms": {"youtube": {"format": "horizontal"}}}
    results = run_enabled_publishers(tmp_path / "vertical.mp4", PublishMeta("id", "Test", tmp_path, tmp_path), cfg, tmp_path)
    assert not results[0].ok
    assert not calls


def test_manual_pack_uses_landscape(tmp_path):
    (tmp_path / "horizontal.mp4").write_bytes(b"landscape")
    (tmp_path / "vertical.mp4").write_bytes(b"vertical")
    cfg = {"platforms": {"rumble": {"enabled": True, "format": "horizontal"}}}
    results = run_enabled_publishers(tmp_path / "vertical.mp4", PublishMeta("id", "Test", tmp_path, tmp_path), cfg, tmp_path)
    assert results[0].status == "manual"
    assert (tmp_path / "for_rumble" / "horizontal.mp4").read_bytes() == b"landscape"


def test_caption_landscape_reuses_clip_transcript(tmp_path, monkeypatch):
    source = tmp_path / "horizontal.mp4"
    srt = tmp_path / "clip-captions-test.srt"
    srt.write_text("captions")
    calls = []
    monkeypatch.setattr("subscript.captions.burn_captions", lambda *a: calls.append(a) or a[2])
    result = maybe_caption_horizontal(source, tmp_path, "test", {"captions": {"enabled": True}})
    assert calls[0][:2] == (source, srt)
    assert result.name == "clip-horizontal-captioned-test.mp4"


def test_format_settings_and_invalid_presets(app_env):
    response = app_env.client.post("/publishing", data={"youtube_format": "horizontal", "rumble_format": "horizontal"}, follow_redirects=False)
    assert "msg=" in response.headers["location"]
    assert app_env.cfg["platforms"]["youtube"]["format"] == "horizontal"
    response = app_env.client.post("/publishing", data={"instagram_format": "unsupported"}, follow_redirects=False)
    assert "err=" in response.headers["location"]
