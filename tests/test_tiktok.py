from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def test_tiktok_authorization_url_uses_desktop_pkce(tmp_path, monkeypatch):
    from subscript.publish import tiktok

    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "test-client")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "test-secret")
    cfg = {"mode": "api", "redirect_uri": "http://127.0.0.1:8787/connections/tiktok/callback"}
    url = tiktok.begin_authorization(cfg)
    query = parse_qs(urlparse(url).query)
    assert query["client_key"] == ["test-client"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 64
    assert query["redirect_uri"] == [cfg["redirect_uri"]]
    assert query["scope"] == ["user.info.basic,video.publish"]
    assert query["state"][0] in tiktok._PENDING_AUTH
    tiktok._PENDING_AUTH.clear()


def test_tiktok_status_never_renders_secret(tmp_path, monkeypatch):
    from subscript.publish.tiktok import connection_status

    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "public-looking-key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "do-not-render-this")
    status = connection_status({"token_file": str(tmp_path / "token.json")})
    assert status["state"] == "disconnected"
    assert "do-not-render-this" not in str(status)


def test_tiktok_direct_post_initializes_file_upload_and_reports_submitted(tmp_path, monkeypatch):
    from subscript.publish import tiktok
    from subscript.publish.base import PublishMeta

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video bytes")
    token = tmp_path / "token.json"
    token.write_text(json.dumps({
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "scope": "user.info.basic,video.publish",
        "expires_at": 9_999_999_999,
    }))
    cfg = {
        "mode": "api",
        "client_key": "client",
        "client_secret": "secret",
        "token_file": str(token),
        "privacy_level": "SELF_ONLY",
    }
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("creator_info/query/"):
            return {"data": {"privacy_level_options": ["SELF_ONLY", "PUBLIC_TO_EVERYONE"]}}
        if url.endswith("video/init/"):
            return {"data": {"publish_id": "publish-1", "upload_url": "https://upload.example/video"}}
        if url.endswith("status/fetch/"):
            return {"data": {"status": "PROCESSING_UPLOAD"}}
        raise AssertionError(url)

    monkeypatch.setattr(tiktok, "_request_json", fake_request)
    monkeypatch.setattr(tiktok, "_upload_file", lambda url, path, size: calls.append(("upload", url, size)))
    monkeypatch.setattr(tiktok.time, "sleep", lambda _: None)
    result = tiktok.TikTokClient(cfg).publish_video(
        video,
        PublishMeta("id", "Big moment", tmp_path, tmp_path, description="Watch this", tags=["gaming"]),
    )
    assert result.ok and result.status == "submitted"
    init = next(item for item in calls if item[1].endswith("video/init/"))
    assert init[2]["body"]["source_info"]["source"] == "FILE_UPLOAD"
    assert init[2]["body"]["post_info"]["privacy_level"] == "SELF_ONLY"
    assert any(item[0] == "upload" for item in calls)


def test_tiktok_connection_route_opens_authorization(app_env, monkeypatch):
    from subscript import publishing_routes

    opened = []
    monkeypatch.setattr(publishing_routes, "begin_authorization", lambda cfg: "https://www.tiktok.com/v2/auth/authorize/?test=1")
    monkeypatch.setattr(publishing_routes.webbrowser, "open", lambda url, **kwargs: opened.append(url))
    response = app_env.client.post("/connections/tiktok/connect", follow_redirects=False)
    assert response.status_code == 303
    assert opened == ["https://www.tiktok.com/v2/auth/authorize/?test=1"]


def test_tiktok_api_mode_and_privacy_save(app_env):
    response = app_env.client.post(
        "/publishing",
        data={"tiktok_enabled": "1", "tiktok_mode": "api", "tiktok_privacy": "SELF_ONLY"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert app_env.cfg["platforms"]["tiktok"]["mode"] == "api"
    assert app_env.cfg["platforms"]["tiktok"]["privacy_level"] == "SELF_ONLY"
