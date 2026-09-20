from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize("exists,valid,refresh,label", [
    (False, False, False, "Not connected"),
    (True, True, True, "Connected"),
    (True, False, True, "Connected"),
    (True, False, False, "Needs attention"),
])
def test_connection_badge_states(tmp_path, monkeypatch, exists, valid, refresh, label):
    from subscript.publishing_routes import youtube_connection_html
    client = tmp_path / "client.json"
    client.touch()
    token = tmp_path / "token.json"
    if exists:
        token.touch()
    monkeypatch.setattr("subscript.publishing_routes.client_secrets_path", lambda cfg: client)
    monkeypatch.setattr("subscript.publishing_routes.token_path", lambda cfg: token)
    def load(*args, **kwargs):
        if not exists:
            raise FileNotFoundError()
        return SimpleNamespace(valid=valid, refresh_token=refresh)
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file", load)
    monkeypatch.setattr("subscript.publishing_routes.dry_run_forced", lambda: False)
    html = youtube_connection_html({"youtube": {"enabled": False}})
    assert f" {label}</span>" in html
    assert "Uploads off" in html
    assert str(token) not in html


def test_preview_mode_separate_from_connected_badge(tmp_path, monkeypatch):
    from subscript.publishing_routes import youtube_connection_html
    client = tmp_path / "client.json"
    client.touch()
    monkeypatch.setattr("subscript.publishing_routes.client_secrets_path", lambda cfg: client)
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file", lambda *a, **kw: SimpleNamespace(valid=True, refresh_token=True))
    monkeypatch.setattr("subscript.publishing_routes.dry_run_forced", lambda: True)
    html = youtube_connection_html({"youtube": {"enabled": True}})
    assert " Connected</span>" in html
    assert "Uploads paused" in html


def test_credentials_are_not_rendered(app_env):
    app_env.cfg["youtube"].update(client_secrets_file="private-client-location.json", token_file="private-token-location.json")
    page = app_env.client.get("/").text
    for forbidden in ("private-client-location", "private-token-location", "Connection files", "coming later", "coming soon", 'name="youtube_secrets"', 'name="youtube_token"'):
        assert forbidden not in page
    assert "No account connection is needed" in page


def test_save_preserves_hidden_connection_configuration(app_env):
    app_env.cfg["youtube"].update(client_secrets_file="custom-client.json", token_file="custom-token.json")
    app_env.client.post("/publishing", data={"youtube_privacy": "private"}, follow_redirects=False)
    assert app_env.cfg["youtube"]["client_secrets_file"] == "custom-client.json"
    assert app_env.cfg["youtube"]["token_file"] == "custom-token.json"


def test_connect_error_does_not_expose_credentials(app_env, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret-token private-file-path")
    monkeypatch.setattr("subscript.publishing_routes.get_youtube_credentials", fail)
    response = app_env.client.post("/connections/youtube/connect", follow_redirects=False)
    assert "err=" in response.headers["location"]
    assert "secret-token" not in response.headers["location"]
    assert "private-file-path" not in response.headers["location"]


def test_connect_does_not_enable_uploads(app_env, monkeypatch):
    calls = []
    monkeypatch.setattr("subscript.publishing_routes.get_youtube_credentials", lambda *a, **kw: calls.append(kw))
    before = app_env.cfg["youtube"]["enabled"]
    response = app_env.client.post("/connections/youtube/connect", follow_redirects=False)
    assert "msg=" in response.headers["location"]
    assert calls == [{"timeout_seconds": 120}]
    assert app_env.cfg["youtube"]["enabled"] == before
