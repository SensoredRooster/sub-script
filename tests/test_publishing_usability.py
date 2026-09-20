from types import SimpleNamespace


def test_connected_account_has_no_check_button(monkeypatch):
    from subscript.publishing_routes import youtube_connection_html
    monkeypatch.setattr("subscript.publishing_routes.youtube_connection_status", lambda cfg: {
        "state": "connected", "label": "Connected", "detail": "Saved", "delivery": "Uploads off", "configured": True})
    html = youtube_connection_html({})
    assert "Connected" in html
    assert "<button" not in html


def test_off_platform_settings_are_hidden(app_env):
    app_env.cfg["youtube"]["enabled"] = False
    app_env.cfg["platforms"] = {"tiktok": {"enabled": False}, "instagram": {"enabled": True}}
    page = app_env.client.get("/").text
    assert 'class="platform-settings form-grid" hidden' in page
    assert 'data-platform="tiktok"' in page
    assert 'class="platform-settings" hidden' in page
    assert "Generate sample titles" in page


def test_sample_generation_selects_destinations_without_saving(app_env):
    response = app_env.client.post("/post-copy/preview", data={"platforms": "youtube,tiktok", "copy_game": "Example"})
    assert response.status_code == 200
    assert [d["platform"] for d in response.json()["drafts"]] == ["YouTube", "TikTok"]
    assert not app_env.cfg_path.exists()
    assert app_env.queue.list() == []
    assert app_env.client.post("/post-copy/preview").status_code == 400


def test_manual_generation_works_with_automation_off_and_preserves_edits(app_env):
    app_env.cfg["post_copy"] = {"enabled": False, "game": "Example"}
    item = app_env.queue.enqueue(app_env.tmp / "clip-branded-test.mp4", app_env.tmp / "source.mp4")
    (app_env.tmp / "clip-captions-test.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nMade it!\n", encoding="utf-8")
    response = app_env.client.post(f"/items/{item.id}/generate-post-copy", follow_redirects=False)
    assert response.status_code == 303
    item = app_env.queue.get(item.id)
    assert len(item.post_metadata) == 6
    assert "Made it!" in item.post_metadata["youtube"]["title"]
    item.post_metadata["youtube"]["title"] = "My edit"
    app_env.queue.update(item)
    app_env.client.post(f"/items/{item.id}/generate-post-copy", follow_redirects=False)
    assert app_env.queue.get(item.id).post_metadata["youtube"]["title"] == "My edit"
    assert app_env.queue.get(item.id).status == "pending"
