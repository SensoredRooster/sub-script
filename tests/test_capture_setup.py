from pathlib import Path
import yaml


def test_setup_saves_and_clears_old_source(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    app_env.cfg["live_source"] = "old.mp4"
    response = app_env.client.post("/capture/setup", data={
        "folder": str(app_env.tmp), "hotkey": "ctrl+alt+c", "seconds": "20",
    }, follow_redirects=False)
    assert "msg=" in response.headers["location"]
    saved = yaml.safe_load(app_env.cfg_path.read_text())
    assert saved["live_source"] == ""
    assert saved["watch_folder"] == str(app_env.tmp.resolve())
    assert saved["hotkey"] == "ctrl+alt+c"
    assert saved["buffer_seconds"] == 20
    assert saved["auto_start_watcher"] is False


def test_setup_test_never_uploads(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    app_env.cfg["review"] = {"require_approval": False}
    (app_env.tmp / "replay.mp4").write_bytes(b"test")
    calls = []
    monkeypatch.setattr("subscript.capture_setup.run_pipeline", lambda *a, **kw: calls.append((a, kw)))
    response = app_env.client.post("/capture/setup", data={
        "folder": str(app_env.tmp), "action": "test",
    }, follow_redirects=False)
    assert "#review" in response.headers["location"]
    assert calls[0][0][1]["review"]["require_approval"] is True
    assert calls[0][1]["dry_run"] is True
    assert app_env.cfg["review"]["require_approval"] is False
    assert not app_env.cfg_path.exists()


def test_setup_invalid_folder_does_not_save(app_env):
    response = app_env.client.post("/capture/setup", data={"folder": str(app_env.tmp / "missing")}, follow_redirects=False)
    assert "err=" in response.headers["location"]
    assert not app_env.cfg_path.exists()


def test_setup_missing_replay_gives_actionable_error(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    response = app_env.client.post("/capture/setup", data={"folder": str(app_env.tmp), "action": "test"}, follow_redirects=False)
    assert "No%20replay" in response.headers["location"]


def test_home_explains_automated_flow_wizard(app_env):
    page = app_env.client.get("/").text
    assert "Set up an automated workflow" in page
    assert "Save &amp; start automated workflow" in page
    assert "Build your posting profiles" in page
    assert 'name="flow_platform"' in page
    assert "Next: connect SubScript" in page
    assert "I saved a test replay" in page
    assert 'name="review_mode"' in page


def test_automatic_flow_requires_a_posting_profile(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    response = app_env.client.post("/capture/setup", data={
        "folder": str(app_env.tmp), "review_mode": "automatic", "flow_profile_setup": "1",
    }, follow_redirects=False)
    assert "Choose%20at%20least%20one%20posting%20profile" in response.headers["location"]
    assert not app_env.cfg_path.exists()


def test_automatic_flow_saves_selected_posting_profile(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    response = app_env.client.post("/capture/setup", data={
        "folder": str(app_env.tmp), "hotkey": "ctrl+alt+c", "seconds": "20",
        "review_mode": "automatic", "flow_profile_setup": "1", "flow_platform": "tiktok",
        "flow_tiktok_mode": "api", "flow_tiktok_format": "vertical",
        "flow_tiktok_title": "{game} highlight", "flow_tiktok_description": "Watch the finish.",
        "flow_tiktok_tags": "gaming,clips", "action": "save",
    }, follow_redirects=False)
    assert response.status_code == 303
    saved = yaml.safe_load(app_env.cfg_path.read_text())
    assert saved["review"]["require_approval"] is False
    assert saved["platforms"]["tiktok"]["enabled"] is True
    assert saved["platforms"]["tiktok"]["mode"] == "api"
    assert saved["platforms"]["tiktok"]["title_template"] == "{game} highlight"
    assert saved["platforms"]["tiktok"]["tags"] == ["gaming", "clips"]


def test_save_and_start_flow_arms_watcher(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")

    class FakeWatcher:
        def start(self):
            self.started = True

    fake = FakeWatcher()
    monkeypatch.setattr("subscript.live_ui.ensure_watcher", lambda holder, cfg: fake)
    response = app_env.client.post(
        "/capture/setup",
        data={
            "folder": str(app_env.tmp),
            "hotkey": "ctrl+alt+c",
            "seconds": "20",
            "review_mode": "automatic",
            "action": "save_and_start",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert fake.started is True
    assert app_env.cfg["review"]["require_approval"] is False
    assert app_env.cfg["auto_start_watcher"] is True
