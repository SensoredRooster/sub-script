import json
import time
import urllib.error

import pytest

from subscript import trends


SEARCH = {"items": [{"id": {"videoId": f"v{i}"}} for i in range(3)]}
VIDEOS = {"items": [
    {"snippet": {"title": "Insane clutch #Warzone #BigWin", "description": "#warzone #rebirth", "tags": ["warzone", "rebirth island"]}},
    {"snippet": {"title": "#BigWin again", "description": "#Rebirth #nsfw", "tags": ["Rebirth Island", "warzone"]}},
    {"snippet": {"title": "solo #OneOff", "description": "", "tags": ["only once"]}},
]}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr("subscript.config.load_dotenv", lambda *a, **k: None)
    return {"trends": {"enabled": True, "sources": ["seeds", "youtube"], "region": "US"}, "output": {"dir": str(tmp_path)}}


def _fake_http(calls):
    def fake(url, params):
        calls.append((url, params))
        assert params["key"] == "test-key"
        return SEARCH if url.endswith("/search") else VIDEOS
    return fake


def test_disabled_by_default_makes_no_network_calls(monkeypatch):
    monkeypatch.setattr(trends, "_http_get_json", lambda *a: pytest.fail("network used"))
    assert trends.get_suggestions({}, "Warzone").basis == "Offline game seeds"


def test_missing_key_falls_back(cfg, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY")
    monkeypatch.setattr(trends, "_http_get_json", lambda *a: pytest.fail("network used"))
    assert "YOUTUBE_API_KEY" in trends.get_suggestions(cfg, "Warzone").basis


def test_youtube_trends_ranked_filtered_and_cached(cfg, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(trends, "_http_get_json", _fake_http(calls))
    s = trends.get_suggestions(cfg, "Warzone")
    assert {h.lower() for h in s.hashtags[:3]} == {"warzone", "bigwin", "rebirth"}
    assert "OneOff" not in s.hashtags and "nsfw" not in [h.lower() for h in s.hashtags]
    assert "rebirth island" in s.keywords
    assert s.basis.startswith("Trend-assisted: YouTube US")
    assert calls[0][1]["videoCategoryId"] == "20" and calls[0][1]["order"] == "viewCount"
    assert (tmp_path / "trends-cache.json").is_file()
    trends.get_suggestions(cfg, "Warzone")
    assert len(calls) == 2  # second call served from the 24h cache


def test_stale_cache_refetch_failure_uses_cache(cfg, monkeypatch, tmp_path):
    (tmp_path / "trends-cache.json").write_text(json.dumps({"youtube:warzone:US": {"fetched_at": time.time() - 3 * 86400, "hashtags": ["OldTag"], "keywords": []}}), encoding="utf-8")
    def boom(*a):
        raise urllib.error.URLError("timed out")
    monkeypatch.setattr(trends, "_http_get_json", boom)
    s = trends.get_suggestions(cfg, "Warzone")
    assert s.hashtags[0] == "OldTag" and "refresh failed" in s.basis


def test_timeout_without_cache_falls_back_to_seeds(cfg, monkeypatch):
    def slow(*a):
        raise TimeoutError()
    monkeypatch.setattr(trends, "_http_get_json", slow)
    s = trends.get_suggestions(cfg, "Warzone")
    assert s.basis.startswith("Offline game seeds") and "unavailable" in s.basis
    assert "Warzone" in s.hashtags


def test_http_helper_uses_five_second_timeout(monkeypatch):
    seen = {}
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"
    def fake_open(req, timeout):
        seen["timeout"] = timeout
        seen["url"] = req.full_url
        return Resp()
    monkeypatch.setattr(trends.urllib.request, "urlopen", fake_open)
    trends._http_get_json("https://www.googleapis.com/youtube/v3/search", {"q": "x"})
    assert seen["timeout"] == 5 and seen["url"].startswith("https://www.googleapis.com/")


def test_generate_posts_uses_trends_when_enabled(cfg, monkeypatch):
    from subscript.post_metadata import generate_posts

    monkeypatch.setattr(trends, "_http_get_json", _fake_http([]))
    posts = generate_posts({**cfg, "post_copy": {"game": "Warzone"}})
    assert "Trend-assisted" in posts["tiktok"]["basis"]
    assert "rebirth island" in posts["youtube"]["tags"]
