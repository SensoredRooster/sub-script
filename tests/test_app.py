"""HTTP-level tests for the review app (FastAPI TestClient, isolated output dir)."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import unquote

import yaml

from tests.conftest import needs_ffmpeg


def _fake_item(env, name: str = "fake", with_captioned: bool = True, master: Path | None = None):
    out = env.out_dir
    out.mkdir(parents=True, exist_ok=True)
    if master is None:
        master = out / f"{name}-master.mp4"
        master.write_bytes(b"\x00" * 64)
    h = out / f"{name}-h.mp4"
    v = out / f"{name}-v.mp4"
    h.write_bytes(b"\x00" * 64)
    v.write_bytes(b"\x00" * 64)
    c = None
    if with_captioned:
        c = out / f"{name}-c.mp4"
        c.write_bytes(b"\x00" * 64)
    return env.queue.enqueue(
        master, out / "src.mp4", title="Fake clip",
        horizontal_path=h, vertical_path=v, vertical_captioned_path=c,
    )


def test_home_renders_all_sections(app_env) -> None:
    r = app_env.client.get("/")
    assert r.status_code == 200
    for needle in ("Bring in your footage", "Live hotkey", "Make it yours", "Choose your destinations", "No clips waiting", "/static/app.js"):
        assert needle in r.text, needle


def test_automatic_clip_uses_highlight(app_env, monkeypatch) -> None:
    source = app_env.tmp / "auto.mp4"
    source.write_bytes(b"video")
    calls = []
    monkeypatch.setattr("subscript.live_app.suggest_highlights_or_fallback",
                        lambda *args, **kwargs: {"suggestions": [{"start": 42, "duration": 18}]})
    monkeypatch.setattr("subscript.live_app.run_pipeline",
                        lambda *args, **kwargs: calls.append(kwargs))
    result = app_env.client.post("/clip", data={"local_path": str(source), "mode": "auto"}, follow_redirects=False)
    assert result.status_code == 303
    assert calls == [{"dry_run": True, "start": 42, "duration": 18.0}]


def test_automatic_clip_falls_back_when_no_highlights(app_env, monkeypatch) -> None:
    source = app_env.tmp / "quiet.mp4"
    source.write_bytes(b"video")
    calls = []
    monkeypatch.setattr("subscript.live_app.suggest_highlights_or_fallback",
                        lambda *args, **kwargs: {"suggestions": []})
    monkeypatch.setattr("subscript.live_app.run_pipeline",
                        lambda *args, **kwargs: calls.append(kwargs))
    app_env.client.post("/clip", data={"local_path": str(source), "mode": "auto"}, follow_redirects=False)
    assert calls[0]["start"] is None
    assert calls[0]["duration"] == float(app_env.cfg.get("buffer_seconds") or 30)


def test_publishing_panel_renders_platform_inputs(app_env) -> None:
    text = app_env.client.get("/").text
    for needle in ("YouTube Shorts", "TikTok", "Instagram", "Facebook", "X / Twitter", "Rumble"):
        assert needle in text
    assert 'name="youtube_title"' in text
    assert 'name="tiktok_enabled"' in text


def test_publishing_save_persists_settings(app_env) -> None:
    r = app_env.client.post(
        "/publishing",
        data={
            "youtube_enabled": "1", "youtube_privacy": "public",
            "youtube_title": "Victory {timestamp}", "youtube_tags": "warzone, win",
            "youtube_category": "20", "youtube_secrets": "credentials.json",
            "youtube_token": "token.json", "instagram_enabled": "1",
            "instagram_mode": "manual", "tiktok_mode": "manual",
            "facebook_mode": "manual", "twitter_mode": "manual", "rumble_mode": "manual",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and "#publish" in r.headers["location"]
    saved = yaml.safe_load(app_env.cfg_path.read_text(encoding="utf-8"))
    assert saved["youtube"]["enabled"] is True
    assert saved["youtube"]["privacy"] == "public"
    assert saved["youtube"]["tags"] == ["warzone", "win"]
    assert saved["platforms"]["instagram"] == {"enabled": True, "mode": "manual"}


def test_publishing_rejects_invalid_youtube_privacy(app_env) -> None:
    r = app_env.client.post(
        "/publishing",
        data={"youtube_privacy": "everyone"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Invalid YouTube privacy setting" in unquote(r.headers["location"])
    assert not app_env.cfg_path.exists()


def test_publishing_values_are_html_escaped(app_env) -> None:
    app_env.cfg["youtube"].update(
        {
            "title_template": '\"><script>alert(1)</script>',
            "description": "<img src=x onerror=alert(1)>",
        }
    )
    text = app_env.client.get("/").text
    assert "<script>alert(1)</script>" not in text
    assert "<img src=x" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_home_banner_escapes_and_links_youtube(app_env) -> None:
    r = app_env.client.get("/", params={"msg": "Uploaded <b>x</b> https://youtu.be/abc123"})
    assert "&lt;b&gt;x&lt;/b&gt;" in r.text
    assert 'href="https://youtu.be/abc123"' in r.text
    r2 = app_env.client.get("/", params={"err": "bad <thing>"})
    assert "bad-banner" in r2.text and "&lt;thing&gt;" in r2.text


def test_home_shows_pending_card_with_captioned_preview(app_env) -> None:
    item = _fake_item(app_env)
    r = app_env.client.get("/")
    assert item.id in r.text
    assert f"/media/{item.id}?variant=captioned" in r.text
    assert "Plain vertical (no captions)" in r.text
    assert "No clips waiting" not in r.text
    assert f"out\\approved\\{item.id}\\" in r.text


def test_home_card_without_captioned_uses_plain_vertical(app_env) -> None:
    item = _fake_item(app_env, with_captioned=False)
    r = app_env.client.get("/")
    assert f"/media/{item.id}?variant=vertical" in r.text
    assert "variant=captioned" not in r.text


def test_media_variants_and_404(app_env) -> None:
    item = _fake_item(app_env)
    for query in ("?variant=horizontal", "?variant=vertical", "?variant=captioned", ""):
        r = app_env.client.get(f"/media/{item.id}{query}")
        assert r.status_code == 200 and len(r.content) == 64, query
    assert app_env.client.get("/media/nope").status_code == 404


def test_reject_then_refuse_second_action(app_env) -> None:
    item = _fake_item(app_env)
    r = app_env.client.post(f"/items/{item.id}/reject", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/?msg=")
    assert app_env.queue.get(item.id).status == "rejected"
    r2 = app_env.client.post(f"/items/{item.id}/approve", follow_redirects=False)
    assert r2.status_code == 303 and "already rejected" in unquote(r2.headers["location"])
    assert app_env.client.get("/").text.count(item.id) == 0


def test_approve_builds_pack_and_manual_platform(app_env) -> None:
    item = _fake_item(app_env)
    r = app_env.client.post(f"/items/{item.id}/approve", follow_redirects=False)
    assert r.status_code == 303
    loc = unquote(r.headers["location"])
    assert loc.startswith("/?msg=")
    assert "YouTube: skipped (disabled)" in loc and "TikTok: manual" in loc
    approved = app_env.out_dir / "approved" / item.id
    for name in ("horizontal.mp4", "vertical.mp4", "vertical_captioned.mp4", "master.mp4", "PLATFORMS.txt", "manifest.json"):
        assert (approved / name).is_file(), name
    assert (approved / "for_tiktok" / "vertical_captioned.mp4").is_file()
    assert (approved / "for_tiktok" / "POST_INSTRUCTIONS.txt").is_file()
    assert app_env.queue.get(item.id).status == "approved"


def test_approve_reports_platform_errors_as_banner(app_env) -> None:
    app_env.cfg["platforms"] = {"twitter": {"enabled": True, "mode": "api"}}
    item = _fake_item(app_env)
    r = app_env.client.post(f"/items/{item.id}/approve", follow_redirects=False)
    assert r.status_code == 303
    loc = unquote(r.headers["location"])
    assert loc.startswith("/?err=") and "not_configured" in loc
    # Pack still saved and item still leaves the pending list (fail-soft).
    assert (app_env.out_dir / "approved" / item.id / "PLATFORMS.txt").is_file()
    assert app_env.queue.get(item.id).status == "approved"


def test_trim_validation_redirects_with_error(app_env) -> None:
    item = _fake_item(app_env)
    r = app_env.client.post(f"/items/{item.id}/trim", data={"start": "5", "end": "5"}, follow_redirects=False)
    assert r.status_code == 303
    assert "End must be greater than start" in unquote(r.headers["location"])
    assert app_env.queue.get(item.id).status == "pending"
    r2 = app_env.client.post(f"/items/{item.id}/trim", data={"start": "-1", "end": "5"}, follow_redirects=False)
    assert "Start must be 0 or greater" in unquote(r2.headers["location"])


def test_unknown_item_actions_404(app_env) -> None:
    for action in ("approve", "reject"):
        assert app_env.client.post(f"/items/nope/{action}", follow_redirects=False).status_code == 404
    assert app_env.client.post("/items/nope/trim", data={"start": "0", "end": "1"}, follow_redirects=False).status_code == 404


def test_clip_without_source_redirects_error(app_env) -> None:
    r = app_env.client.post("/clip", data={"mode": "last30"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Drop or choose a video file" in unquote(r.headers["location"])
    r2 = app_env.client.post("/clip", data={"mode": "last30", "local_path": str(app_env.tmp / "nope.mp4")}, follow_redirects=False)
    assert "File not found on this PC" in unquote(r2.headers["location"])
    r3 = app_env.client.post("/clip", data={"mode": "custom", "local_path": str(app_env.tmp / "nope.txt")}, follow_redirects=False)
    assert "Unsupported video type" in unquote(r3.headers["location"]) or "File not found" in unquote(r3.headers["location"])


def test_highlights_fallback_without_source(app_env) -> None:
    r = app_env.client.post("/highlights", data={"top_n": "3"})
    assert r.status_code == 200
    j = r.json()
    assert j["fallback"] is True and j["suggestions"][0]["start"] is None
    assert j["buffer_seconds"] == 30.0


def test_live_status_and_start_without_source(app_env) -> None:
    r = app_env.client.get("/live/status")
    assert r.status_code == 200
    j = r.json()
    assert j["armed"] is False and j["hotkey"] == "ctrl+shift+c" and "source_hint" in j
    r2 = app_env.client.post("/live/start")
    assert r2.status_code == 400 and "No live source configured" in r2.json()["last_error"]
    r3 = app_env.client.post("/live/stop")
    assert r3.status_code == 200 and r3.json()["armed"] is False


def test_api_brand_and_logo(app_env) -> None:
    j = app_env.client.get("/api/brand").json()
    for key in ("logo_path", "position", "opacity", "margin_px", "has_logo", "captions_enabled", "captions_engine", "music_enabled", "music_volume", "has_music", "whisper_available"):
        assert key in j, key
    assert j["captions_engine"] == "demo"
    assert j["music_enabled"] is False
    r = app_env.client.get("/brand/logo")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_brand_save_persists_to_isolated_config(app_env) -> None:
    r = app_env.client.post(
        "/brand",
        data={
            "position": "top_left", "opacity": "0.5", "margin_px": "10",
            "captions_enabled": "1", "captions_engine": "whisper",
            "music_volume": "0.2",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].startswith("/?msg=")
    saved = yaml.safe_load(app_env.cfg_path.read_text(encoding="utf-8"))
    assert saved["brand"]["position"] == "top_left" and saved["brand"]["opacity"] == 0.5
    assert saved["captions"] == {"enabled": True, "engine": "whisper"}
    assert saved["music"]["enabled"] is False and saved["music"]["volume"] == 0.2
    j = app_env.client.get("/api/brand").json()
    assert j["position"] == "top_left" and j["captions_engine"] == "whisper"


def test_brand_save_rejects_bad_values(app_env) -> None:
    r = app_env.client.post("/brand", data={"position": "middle", "opacity": "0.5", "margin_px": "10"}, follow_redirects=False)
    assert "Position must be" in unquote(r.headers["location"])
    r2 = app_env.client.post("/brand", data={"position": "top_left", "opacity": "5", "margin_px": "10"}, follow_redirects=False)
    assert "Opacity must be" in unquote(r2.headers["location"])
    assert not app_env.cfg_path.exists()


@needs_ffmpeg
def test_full_clip_flow_then_trim_and_approve(app_env, synth_video: Path) -> None:
    client = app_env.client
    r = client.post(
        "/clip",
        data={"local_path": str(synth_video), "mode": "custom", "start": "0", "duration": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"].startswith("/?msg="), unquote(r.headers["location"])
    pending = app_env.queue.list(status="pending")
    assert len(pending) == 1
    item = pending[0]
    for attr in ("video_path", "horizontal_path", "vertical_path", "vertical_captioned_path"):
        value = getattr(item, attr)
        assert value and Path(value).is_file(), attr

    home = client.get("/").text
    assert f"/media/{item.id}?variant=captioned" in home

    # Highlights on a real file returns analysed windows (not the fallback).
    hl = client.post("/highlights", data={"local_path": str(synth_video), "top_n": "2", "buffer_seconds": "1"}).json()
    assert hl["fallback"] is False and hl["suggestions"] and hl["suggestions"][0]["start"] is not None

    # Trim from the master, then approve the trimmed result.
    r2 = client.post(f"/items/{item.id}/trim", data={"start": "0.2", "end": "0.8"}, follow_redirects=False)
    assert r2.status_code == 303 and r2.headers["location"].startswith("/?msg="), unquote(r2.headers["location"])
    trimmed = app_env.queue.get(item.id)
    assert trimmed.status == "pending" and trimmed.trim_start == 0.2 and trimmed.trim_end == 0.8
    assert trimmed.video_path == item.video_path  # master preserved
    assert trimmed.edited_path and Path(trimmed.edited_path).is_file()
    assert Path(trimmed.horizontal_path).is_file() and Path(trimmed.vertical_captioned_path).is_file()
    assert "Trimmed 0.2s" in client.get("/").text

    r3 = client.post(f"/items/{item.id}/approve", follow_redirects=False)
    assert r3.status_code == 303 and r3.headers["location"].startswith("/?msg=")
    approved = app_env.out_dir / "approved" / item.id
    assert (approved / "master.mp4").stat().st_size == Path(trimmed.edited_path).stat().st_size
    assert (approved / "vertical_captioned.mp4").is_file()


@needs_ffmpeg
def test_upload_path_copies_into_uploads_dir(app_env, synth_video: Path) -> None:
    with synth_video.open("rb") as fh:
        r = app_env.client.post(
            "/clip",
            data={"mode": "custom", "start": "0", "duration": "1"},
            files={"file": ("my clip.mp4", fh, "video/mp4")},
            follow_redirects=False,
        )
    assert r.status_code == 303 and r.headers["location"].startswith("/?msg="), unquote(r.headers["location"])
    uploads = list((app_env.out_dir / "uploads").glob("*_my_clip.mp4"))
    assert len(uploads) == 1
    shutil.rmtree(app_env.out_dir / "uploads", ignore_errors=True)
