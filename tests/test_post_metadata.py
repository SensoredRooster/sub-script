import json
from pathlib import Path

from subscript.post_metadata import generate_posts, transcript_text
from subscript.publish import PublishMeta
from subscript.publish.orchestrator import run_enabled_publishers


def test_demo_captions_never_become_post_copy(tmp_path):
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nClip | SUB\n", encoding="utf-8")
    posts = generate_posts({"post_copy": {"game": "Warzone"}}, srt)
    assert transcript_text(srt) == ""
    assert "SUB" not in json.dumps(posts)
    assert posts["youtube"]["title"] == "Warzone highlight"
    assert len({post["description"] for post in posts.values()}) == 6


def test_real_transcript_used_and_bounded(tmp_path):
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nWe made it across!\n", encoding="utf-8")
    posts = generate_posts({"post_copy": {"game": "Example", "creator": "Sam"}}, srt)
    assert "We made it across!" in posts["youtube"]["title"]
    assert len(posts["twitter"]["description"]) <= 260
    assert all(len(post["title"]) <= 95 for post in posts.values())
    assert generate_posts({"post_copy": {"enabled": False}}, srt) == {}


def test_manual_pack_contains_platform_copy(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    drafts = generate_posts({})
    approved = tmp_path / "approved"
    meta = PublishMeta("id", "old title", tmp_path, approved, extra={"post_metadata": drafts})
    results = run_enabled_publishers(video, meta, {"platforms": {"tiktok": {"enabled": True}}}, tmp_path)
    assert results[0].status == "manual"
    saved = (approved / "for_tiktok" / "POST_COPY.txt").read_text(encoding="utf-8")
    assert drafts["tiktok"]["description"] in saved
    assert json.loads((approved / "post-copy.json").read_text())["youtube"] == drafts["youtube"]


def test_youtube_receives_edited_copy_and_literal_braces(tmp_path, monkeypatch):
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    calls = []
    monkeypatch.setattr("subscript.publish.youtube.upload_youtube", lambda path, cfg: calls.append(cfg) or {"title": "ok"})
    draft = {"title": "A {moment}", "description": "My edited description", "tags": ["Example"]}
    meta = PublishMeta("id", "old", tmp_path, tmp_path / "approved", extra={"post_metadata": {"youtube": draft}})
    run_enabled_publishers(tmp_path / "clip.mp4", meta, {"youtube": {"enabled": True, "title_template": "old"}}, tmp_path)
    assert calls[0]["title_template"].format(timestamp="unused") == "A {moment}"
    assert calls[0]["description"] == draft["description"]
    assert calls[0]["tags"] == draft["tags"]


def test_review_editor_saves_and_escapes_copy(app_env):
    item = app_env.queue.enqueue(app_env.tmp / "clip.mp4", app_env.tmp / "source.mp4", post_metadata=generate_posts({}))
    response = app_env.client.post(f"/items/{item.id}/post-copy", data={"platform": "youtube", "title": "<script>test</script>", "description": "Edited", "tags": "one, two"}, follow_redirects=False)
    assert "msg=" in response.headers["location"]
    saved = app_env.queue.get(item.id).post_metadata["youtube"]
    assert saved["tags"] == ["one", "two"]
    page = app_env.client.get("/clip").text
    assert "&lt;script&gt;test&lt;/script&gt;" in page
    assert "<script>test</script>" not in page
    app_env.queue.set_status(item.id, "approved")
    response = app_env.client.post(f"/items/{item.id}/post-copy", data={"platform": "youtube", "title": "late"}, follow_redirects=False)
    assert "err=" in response.headers["location"]


def test_writing_settings_persist(app_env):
    response = app_env.client.post("/publishing", data={"copy_enabled": "1", "copy_game": "Example", "copy_creator": "Sam", "copy_tone": "direct"}, follow_redirects=False)
    assert "msg=" in response.headers["location"]
    assert app_env.cfg["post_copy"] == {"enabled": True, "game": "Example", "creator": "Sam", "tone": "direct"}
