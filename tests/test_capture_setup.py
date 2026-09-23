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


def test_home_routes_to_the_two_clear_workflows(app_env):
    page = app_env.client.get("/").text
    assert "Create &amp; Publish a Clip" in page
    assert "Put My Content on Autopilot" in page
    assert 'href="/clip"' in page
    assert 'href="/automation"' in page


def test_automation_management_lists_profiles(app_env):
    app_env.cfg["automation_profiles"] = [{
        "id": "existing", "name": "Main stream", "folder": str(app_env.tmp),
        "hotkey": "ctrl+alt+c", "buffer_seconds": 20, "enabled": False,
        "platforms": {"tiktok": {"enabled": True}},
    }]
    page = app_env.client.get("/automation").text
    assert "Main stream" in page
    assert str(app_env.tmp) in page
    assert "TikTok" in page
    assert "Start watching" in page


def test_automation_management_can_start_and_stop_a_profile(app_env, monkeypatch):
    app_env.cfg["automation_profiles"] = [{
        "id": "existing", "name": "Main stream", "folder": str(app_env.tmp),
        "hotkey": "ctrl+alt+c", "buffer_seconds": 20, "enabled": False,
        "platforms": {},
    }]

    class FakeWatcher:
        armed = False

        def start(self):
            self.armed = True

    fake = FakeWatcher()
    monkeypatch.setattr("subscript.live_ui.ensure_profile_watcher", lambda *args: fake)
    monkeypatch.setattr("subscript.live_ui.stop_profile_watcher", lambda *args: None)

    started = app_env.client.post("/automation/existing/start", follow_redirects=False)
    assert started.status_code == 303
    assert app_env.cfg["automation_profiles"][0]["enabled"] is True
    assert "watching" in app_env.client.get("/automation").text

    stopped = app_env.client.post("/automation/existing/stop", follow_redirects=False)
    assert stopped.status_code == 303
    assert app_env.cfg["automation_profiles"][0]["enabled"] is False


def test_automation_profile_is_a_separate_slideshow(app_env):
    page = app_env.client.get("/automation/new").text
    assert page.count('data-automation-step=') == 6
    assert "Where will new clips appear?" in page
    assert "Activate workflow" in page
    assert "No extra trigger required" in page
    assert "watches for new videos automatically" in page


def test_automation_profile_saves_by_folder(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    response = app_env.client.post("/automation/save", data={
        "profile_name": "Main stream", "folder": str(app_env.tmp), "hotkey": "ctrl+alt+c",
        "seconds": "20", "source_mode": "whole_file", "review_mode": "review", "action": "save",
    }, follow_redirects=False)
    assert response.status_code == 303
    saved = yaml.safe_load(app_env.cfg_path.read_text())
    assert saved["automation_profiles"][0]["name"] == "Main stream"
    assert saved["automation_profiles"][0]["folder"] == str(app_env.tmp.resolve())
    assert saved["automation_profiles"][0]["enabled"] is False
    assert saved["automation_profiles"][0]["source_mode"] == "whole_file"
    assert "Main stream" in app_env.client.get("/automation").text


def test_automation_profile_persists_normalized_vertical_layout(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    response = app_env.client.post("/automation/save", data={
        "profile_name": "Vertical stream", "folder": str(app_env.tmp), "hotkey": "ctrl+alt+c",
        "seconds": "20", "review_mode": "review", "action": "save",
        "vertical_layout_mode": "composer", "vertical_preset": "facecam_overlay",
        "gameplay_x": "0.05", "gameplay_y": "0", "gameplay_w": "0.7", "gameplay_h": "1",
        "facecam_x": "0.8", "facecam_y": "0.1", "facecam_w": "0.4", "facecam_h": "0.3",
    }, follow_redirects=False)
    assert response.status_code == 303
    saved = yaml.safe_load(app_env.cfg_path.read_text())
    layout = saved["automation_profiles"][0]["vertical_layout"]
    assert layout["mode"] == "composer"
    assert layout["preset"] == "facecam_overlay"
    assert layout["regions"]["facecam"] == {"x": 0.8, "y": 0.1, "w": 0.2, "h": 0.3}


def test_automation_profile_rejects_duplicate_folder(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    app_env.cfg["automation_profiles"] = [{"id": "existing", "name": "Existing", "folder": str(app_env.tmp)}]
    response = app_env.client.post("/automation/save", data={
        "profile_name": "Second", "folder": str(app_env.tmp), "hotkey": "ctrl+alt+c",
        "seconds": "20", "review_mode": "review", "action": "save",
    }, follow_redirects=False)
    assert "already%20belongs%20to%20another" in response.headers["location"]


def test_automation_profile_delete_returns_home(app_env, monkeypatch):
    monkeypatch.setattr("subscript.capture_setup.find_ffmpeg", lambda: "ffmpeg")
    app_env.cfg["automation_profiles"] = [{"id": "existing", "name": "Existing", "folder": str(app_env.tmp)}]
    response = app_env.client.post("/automation/delete", data={"profile_id": "existing"}, follow_redirects=False)
    assert response.status_code == 303
    assert app_env.cfg["automation_profiles"] == []


def test_automation_profile_edit_shows_delete_control(app_env):
    app_env.cfg["automation_profiles"] = [{"id": "existing", "name": "Existing", "folder": str(app_env.tmp)}]
    page = app_env.client.get("/automation/existing/edit").text
    assert "Edit automated profile" in page
    assert "Delete this profile" in page


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
