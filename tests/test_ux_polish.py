import json
import time

from subscript.post_metadata import editor_html, generate_posts
from subscript.secure_store import token_exists, write_token_text
from subscript.trends import detect_game, display_hashtag, trend_status


def test_display_hashtag_camel_case_rules():
    assert display_hashtag("callofduty") == "CallOfDuty"          # seed casing
    assert display_hashtag("rebirthisland") == "RebirthIsland"    # dictionary split
    assert display_hashtag("warzoneclips") == "WarzoneClips"
    assert display_hashtag("bigthing", original="BigThing") == "BigThing"  # original mixed casing kept
    for untouched in ("fyp", "mw3", "bo6", "xyzqwerty"):
        assert display_hashtag(untouched).lower() == untouched    # never split or mangled
    assert display_hashtag("mw3") == "mw3"
    assert display_hashtag("nsfw") == ""


def test_detect_game_is_conservative():
    assert detect_game([r"C:\clips\Warzone\Replay 2026.mp4"]) == "Warzone"
    assert detect_game(["Rocket_League-2026.mp4"]) == "Rocket League"
    assert detect_game(["call of duty warzone"]) == "Warzone"
    assert detect_game(["Replay 2026-09-19 18-46-51.mp4"]) is None
    assert detect_game(["fortnite vs apex legends"]) is None      # ambiguous
    assert detect_game(["my cs val clip"]) is None                 # short codes ignored


def test_blank_game_uses_detected_game_with_label():
    posts = generate_posts({"post_copy": {"game": ""}}, hints=[r"D:\Warzone\clip.mp4"])
    assert "Warzone" in posts["youtube"]["title"]
    assert "Game detected from file name: Warzone" in posts["tiktok"]["basis"]
    plain = generate_posts({"post_copy": {"game": ""}}, hints=["Replay.mp4"])
    assert "Gameplay" in plain["youtube"]["title"]


def test_trend_status_reports_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr("subscript.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    cfg = {"trends": {"enabled": True}, "output": {"dir": str(tmp_path)}}
    st = trend_status(cfg)
    assert st["enabled"] and not st["has_key"] and st["last_updated"] is None
    (tmp_path / "trends-cache.json").write_text(json.dumps({"k": {"fetched_at": time.time() - 7200}}), encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret-value")
    st = trend_status(cfg)
    assert st["has_key"] and st["age"] == "2h ago"
    assert "secret-value" not in json.dumps(st)


def test_publishing_page_shows_trend_status(app_env, monkeypatch):
    monkeypatch.setattr("subscript.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    page = app_env.client.get("/clip").text
    assert "Trend suggestions:" in page
    assert 'id="post-writing"' in page


def test_disconnect_deletes_tokens(app_env, tmp_path):
    yt = tmp_path / "yt-token.json"
    tt = tmp_path / "tt-token.json"
    app_env.cfg["youtube"]["token_file"] = str(yt)
    app_env.cfg["platforms"]["tiktok"]["token_file"] = str(tt)
    write_token_text(yt, "{}")
    write_token_text(tt, json.dumps({"access_token": "a"}))
    r1 = app_env.client.post("/connections/youtube/disconnect", follow_redirects=False)
    r2 = app_env.client.post("/connections/tiktok/disconnect", follow_redirects=False)
    assert r1.status_code == 303 and r2.status_code == 303
    assert not token_exists(yt) and not token_exists(tt)


def test_game_prompt_and_set_game(app_env):
    app_env.cfg["post_copy"] = {"enabled": True, "game": ""}
    item = app_env.queue.enqueue(app_env.tmp / "Warzone" / "clip-branded-x.mp4", app_env.tmp / "Warzone" / "source.mp4")
    html = editor_html(app_env.queue.get(item.id), app_env.cfg)
    assert "Use Warzone" in html
    resp = app_env.client.post("/post-copy/game", data={"game": "Warzone", "item_id": item.id}, follow_redirects=False)
    assert resp.status_code == 303 and "msg=" in resp.headers["location"]
    assert app_env.cfg["post_copy"]["game"] == "Warzone"
    assert editor_html(app_env.queue.get(item.id), app_env.cfg).count("Use Warzone") == 0
    bad = app_env.client.post("/post-copy/game", data={"game": "<script>"}, follow_redirects=False)
    assert "err=" in bad.headers["location"]
