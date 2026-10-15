from subscript.post_metadata import EDITED_BASIS, PLATFORM_LIMITS, generate_posts, merge_drafts
from subscript.trends import clean_hashtag, load_seeds, seed_suggestions


def test_seed_file_loads_with_games_and_emojis():
    seeds = load_seeds()
    assert "warzone" in seeds["games"]
    assert seed_suggestions("Warzone").emojis


def test_game_alias_match_and_generic_fallback():
    assert "Warzone" in seed_suggestions("cod warzone").hashtags
    generic = seed_suggestions("Some Indie Game")
    assert generic.basis == "Offline gaming seeds"
    assert "Gaming" in generic.hashtags


def test_clean_hashtag_rejects_junk():
    assert clean_hashtag("#Warzone") == "Warzone"
    assert clean_hashtag("nsfw") == ""
    assert clean_hashtag("x") == ""


def test_drafts_respect_platform_limits_and_carry_suggestions():
    posts = generate_posts({"post_copy": {"game": "Warzone"}})
    for key, post in posts.items():
        limits = PLATFORM_LIMITS[key]
        assert len(post["title"]) <= limits["title"]
        assert len(post["description"]) <= limits["description"]
        assert len(post["tags"]) <= limits["tags"]
        hashtags = [w for w in post["description"].split() if w.startswith("#") and w not in ("#Shorts", "#GamingClips")]
        assert len(hashtags) <= limits["hashtags"], key
        assert "Offline game seeds" in post["basis"]
        assert post["suggestions"]["emojis"]
    assert "#Warzone" in posts["tiktok"]["description"]
    # emojis are suggestions only, never auto-inserted
    assert not any(e in posts["tiktok"]["description"] for e in posts["tiktok"]["suggestions"]["emojis"])


def test_merge_never_overwrites_user_edits():
    edited = {"title": "Mine", "description": "d", "tags": [], "basis": EDITED_BASIS}
    auto = {"title": "old", "description": "d", "tags": [], "basis": "Creator settings only"}
    merged = merge_drafts({"youtube": edited, "tiktok": auto}, {"youtube": {"title": "new"}, "tiktok": {"title": "new"}})
    assert merged["youtube"] is edited
    assert merged["tiktok"]["title"] == "new"


def test_refresh_route_keeps_edited_and_editor_shows_chips(app_env):
    app_env.cfg["post_copy"] = {"enabled": True, "game": "Fortnite"}
    item = app_env.queue.enqueue(app_env.tmp / "clip-branded-x.mp4", app_env.tmp / "source.mp4", post_metadata=generate_posts(app_env.cfg))
    app_env.client.post(f"/items/{item.id}/post-copy", data={"platform": "youtube", "title": "My title", "description": "Mine", "tags": "a"}, follow_redirects=False)
    resp = app_env.client.post(f"/items/{item.id}/refresh-post-copy", follow_redirects=False)
    assert resp.status_code == 303 and "msg=" in resp.headers["location"]
    saved = app_env.queue.get(item.id).post_metadata
    assert saved["youtube"]["title"] == "My title" and saved["youtube"]["basis"] == EDITED_BASIS
    assert saved["youtube"]["suggestions"]["hashtags"]
    assert "Offline game seeds" in saved["tiktok"]["basis"]
    page = app_env.client.get("/clip").text
    assert 'class="chip"' in page
    assert "Open TikTok Creative Center" in page
    assert app_env.queue.get(item.id).status == "pending"


def test_save_enforces_per_platform_tag_limit(app_env):
    item = app_env.queue.enqueue(app_env.tmp / "clip.mp4", app_env.tmp / "source.mp4", post_metadata=generate_posts({}))
    resp = app_env.client.post(f"/items/{item.id}/post-copy", data={"platform": "twitter", "title": "t", "description": "d", "tags": "a,b,c"}, follow_redirects=False)
    assert "err=" in resp.headers["location"]
