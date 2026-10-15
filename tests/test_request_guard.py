from fastapi import FastAPI
from fastapi.testclient import TestClient

from subscript.request_guard import install_request_guard, is_cross_site_write


def _client() -> TestClient:
    app = FastAPI()
    install_request_guard(app)

    @app.post("/act")
    def act() -> dict:
        return {"ok": True}

    @app.get("/read")
    def read() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_non_browser_post_allowed():
    assert _client().post("/act").status_code == 200


def test_same_origin_and_loopback_posts_allowed():
    c = _client()
    assert c.post("/act", headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert c.post("/act", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200
    assert c.post("/act", headers={"Origin": "http://localhost:3000", "Sec-Fetch-Site": "same-site"}).status_code == 200


def test_cross_site_posts_blocked():
    c = _client()
    assert c.post("/act", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/act", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post("/act", headers={"Origin": "null"}).status_code == 403
    assert c.post("/act", headers={"Origin": "http://127.0.0.1.evil.example"}).status_code == 403


def test_safe_methods_never_blocked():
    c = _client()
    assert c.get("/read", headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}).status_code == 200
    assert not is_cross_site_write("GET", {"sec-fetch-site": "cross-site"})


def test_real_app_blocks_cross_site_post_but_allows_local(app_env):
    paths = [r.path for r in app_env.client.app.routes if "POST" in getattr(r, "methods", set()) and "{" not in r.path]
    assert paths, "expected POST routes"
    for path in paths:
        resp = app_env.client.post(path, headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403, path
    # A same-origin request reaches the route (any non-403 status is fine here).
    ok = app_env.client.post(paths[0], headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"})
    assert ok.status_code != 403 or ok.json().get("detail") != "Cross-site request blocked."
