"""Cloudflare feed checks and silent in-place installs. Network and processes are faked."""

from __future__ import annotations

import hashlib
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from subscript import app_update
from subscript import __version__ as APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
BODY = b"MZ"


def _release(tag="v0.2.0", url=None, name=None, body=BODY):
    version = tag[1:] if tag[:1] in "vV" else tag
    filename = name or f"SubScript-Setup-{version}.exe"
    if url is None:
        url = f"{app_update.FEED_ASSET_PREFIX}{filename}"
    return {"version": version, "url": url, "sha256": hashlib.sha256(body).hexdigest(), "notes": ""}


class _FakeResponse:
    """Minimal stand-in for the object urllib returns from opener.open()."""

    def __init__(self, body: bytes = b"", status: int = 200, url: str = "", headers: dict | None = None):
        self._body = body
        self._pos = 0
        self.status = status
        self._url = url
        self.headers = headers if headers is not None else {}

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = len(self._body) - self._pos
        chunk = self._body[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeOpener:
    def __init__(self, handler):
        self._handler = handler

    def open(self, request, timeout=None):
        return self._handler(request)


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", {}, None)


def _service(tmp_path, **kwargs):
    calls = {"launch": [], "shutdown": 0, "downloads": []}

    def launch(command):
        calls["launch"].append(command)

    def shutdown():
        calls["shutdown"] += 1

    payload = kwargs.pop("payload", _release())
    values = dict(
        version="0.1.0",
        frozen=True,
        platform_name="win32",
        fetch_json=lambda url: payload,
        download=lambda url, dest, progress: calls["downloads"].append((url, dest)) or dest.write_bytes(b"MZ"),
        launch=launch,
        shutdown=shutdown,
        synchronous=True,
        temp_factory=lambda: tmp_path,
    )
    values.update(kwargs)
    return app_update.UpdateService(**values), calls


def test_version_order_is_numeric():
    assert app_update.parse_version("v0.10.0") > app_update.parse_version("0.9.0")
    assert app_update.parse_version("V0.6.0") == app_update.parse_version("0.6.0")
    with pytest.raises(app_update.UpdateError):
        app_update.parse_version("0.6")
    assert app_update.parse_version("v0.6.1-efe5e4b") == (0, 6, 1)
    assert app_update.parse_version("v0.7.0.1") == (0, 7, 0, 1) > app_update.parse_version("0.7.0")
    assert app_update.parse_version("0.7.1") > app_update.parse_version("0.7.0.1")
    assert app_update.parse_version(APP_VERSION)
    with pytest.raises(app_update.UpdateError):
        app_update.parse_version("../0.6.1")


def test_setup_filename_matches_installer_output():
    assert app_update.setup_filename("0.2.0") == "SubScript-Setup-0.2.0.exe"
    assert app_update.is_setup_filename("SubScript-Setup-0.2.0.exe")
    assert app_update.is_setup_filename("SubScript-Setup-0.2.0.exe", "0.2.0")
    assert not app_update.is_setup_filename("SubScript-Setup-0.2.0.exe", "0.3.0")
    assert not app_update.is_setup_filename("SubScript-Setup-0.2.0.exe.exe", "0.2.0")
    assert not app_update.is_setup_filename("Other-Setup-0.2.0.exe")
    assert not app_update.is_setup_filename("SubScript-Setup-0.2.0-x64.exe")


def test_up_to_date(tmp_path):
    service, calls = _service(tmp_path, payload=_release("v0.1.0"))
    status = service.check()
    assert status["message"] == "You're up to date (0.1.0)"
    assert status["state"] == "up_to_date"
    assert status["current"] == "0.1.0"
    assert status["latest"] == "0.1.0"
    assert status["update_available"] is False
    assert status["can_install"] is False
    assert "asset_url" not in status
    with pytest.raises(app_update.UpdateError):
        service.start_install()
    assert calls["launch"] == []
    assert calls["shutdown"] == 0


def test_newer_release_on_installed_windows_app_can_install(tmp_path):
    service, calls = _service(tmp_path)
    status = service.check()
    assert status["message"] == "version 0.2.0 available"
    assert status["update_available"] is True
    assert status["install_supported"] is True
    assert status["can_install"] is True
    assert status["asset_name"] == "SubScript-Setup-0.2.0.exe"
    job = service.start_install()
    assert job["state"] == "installing"
    assert "0.2.0" in job["message"]
    assert calls["shutdown"] == 1
    assert len(calls["launch"]) == 1
    command = calls["launch"][0]
    assert command[1:] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    assert command[0].endswith("SubScript-Setup-0.2.0.exe")
    assert Path(command[0]).parent == tmp_path
    assert calls["downloads"][0][0] == f"{app_update.FEED_ASSET_PREFIX}SubScript-Setup-0.2.0.exe"


def test_source_checkout_shows_version_but_refuses_install(tmp_path):
    service, calls = _service(tmp_path, frozen=False)
    status = service.check()
    assert status["message"] == "version 0.2.0 available"
    assert status["install_supported"] is False
    assert status["can_install"] is False
    with pytest.raises(app_update.UpdateError, match="Windows app"):
        service.start_install()
    assert calls["launch"] == []
    assert calls["downloads"] == []


def test_non_windows_frozen_build_refuses_install(tmp_path):
    service, calls = _service(tmp_path, platform_name="linux")
    assert service.check()["can_install"] is False
    with pytest.raises(app_update.UpdateError):
        service.start_install()
    assert calls["launch"] == []


def test_offline_and_missing_releases_are_quiet(tmp_path):
    offline, _ = _service(tmp_path, fetch_json=lambda url: (_ for _ in ()).throw(app_update.Offline()))
    status = offline.check()
    assert status["state"] == "offline"
    assert status["message"] == "offline"
    assert status["update_available"] is False
    assert status["latest"] is None

    empty, calls = _service(tmp_path, fetch_json=lambda url: (_ for _ in ()).throw(app_update.NoReleases()))
    status = empty.check()
    assert status["state"] == "no_releases"
    assert status["message"] == "no releases"
    job = empty.start_install()
    assert job["state"] == "error"
    assert job["message"] == "no releases"
    assert calls["launch"] == []
    assert calls["shutdown"] == 0


def test_older_remote_release_is_up_to_date(tmp_path):
    service, _ = _service(tmp_path, payload=_release("v0.0.9"))
    assert service.check()["message"] == "You're up to date (0.1.0)"


@pytest.mark.parametrize("url", [
    "http://subscript-updates.sensoredrooster-com.workers.dev/releases/SubScript-Setup-0.2.0.exe",
    "ftp://subscript-updates.sensoredrooster-com.workers.dev/releases/SubScript-Setup-0.2.0.exe",
    "https://evil.example/releases/SubScript-Setup-0.2.0.exe",
    "https://objects.example.com/release-assets/SubScript-Setup-0.2.0.exe",
    "https://subscript-updates.sensoredrooster-com.workers.dev/releases/source.zip",
    "https://subscript-updates.sensoredrooster-com.workers.dev/releases/Other-Setup-0.2.0.exe",
    "https://user:token@subscript-updates.sensoredrooster-com.workers.dev/releases/SubScript-Setup-0.2.0.exe",
    "https://subscript-updates.sensoredrooster-com.workers.dev/releases/nested/SubScript-Setup-0.2.0.exe",
])
def test_rejects_asset_urls_that_are_not_feed_setup_exe(tmp_path, url):
    service, calls = _service(tmp_path, payload=_release(url=url))
    status = service.check()
    assert status["state"] == "error"
    assert status["can_install"] is False
    assert status["asset_name"] is None
    job = service.start_install()
    assert job["state"] == "error"
    assert calls["downloads"] == []
    assert calls["launch"] == []


def test_http_urls_fail_closed_with_clear_error(tmp_path):
    http_url = app_update.FEED_ASSET_PREFIX.replace("https:", "http:") + "SubScript-Setup-0.2.0.exe"
    with pytest.raises(app_update.UpdateError, match="HTTPS"):
        app_update.require_feed_asset_url(http_url)
    with pytest.raises(app_update.UpdateError, match="HTTPS"):
        app_update.interpret_feed(_release(url=http_url), "0.1.0", install_supported=True)

    def never(request):
        raise AssertionError("should not request")

    with pytest.raises(app_update.UpdateError):
        app_update.download_asset(http_url, tmp_path / "unused.exe", None, opener=_FakeOpener(never))
    with pytest.raises(app_update.UpdateError):
        app_update.default_fetch_json(app_update.FEED_URL.replace("https:", "http:"), opener=_FakeOpener(never))


def test_no_github_fallback(tmp_path):
    seen = []

    def fetch(url):
        seen.append(url)
        raise app_update.UpdateError("Could not read the update feed.")

    service, calls = _service(tmp_path, fetch_json=fetch)
    status = service.check()
    assert seen == [app_update.FEED_URL]
    assert status["state"] == "error" and status["can_install"] is False
    assert service.start_install()["state"] == "error"
    assert calls["downloads"] == [] and calls["launch"] == []
    source = (ROOT / "subscript" / "app_update.py").read_text(encoding="utf-8")
    for needle in ("api.github.com", "github.com/", "githubusercontent", "LATEST_RELEASE_URL", "DEFAULT_REPO"):
        assert needle not in source


def test_feed_redirect_is_rejected():
    def redirect(request):
        raise _http_error(request.full_url, 302)

    with pytest.raises(app_update.UpdateError, match="redirect"):
        app_update.default_fetch_json(app_update.FEED_URL, opener=_FakeOpener(redirect))


def test_download_redirect_is_rejected(tmp_path):
    asset = f"{app_update.FEED_ASSET_PREFIX}SubScript-Setup-0.2.0.exe"
    seen = []

    def handler(request):
        seen.append(request.full_url)
        raise _http_error(request.full_url, 302)

    dest = tmp_path / "SubScript-Setup-0.2.0.exe"
    with pytest.raises(app_update.UpdateError, match="redirect"):
        app_update.download_asset(asset, dest, None, opener=_FakeOpener(handler))
    assert seen == [asset]
    assert not dest.exists() and not list(tmp_path.glob("*.part"))


def test_sha256_mismatch_is_rejected(tmp_path):
    service, calls = _service(tmp_path, payload=_release(body=b"expected"))
    service.start_install()
    assert service.job()["state"] == "error"
    assert "checksum" in service.job()["message"]
    assert calls["launch"] == [] and calls["shutdown"] == 0
    assert not (tmp_path / "SubScript-Setup-0.2.0.exe").exists()


def test_missing_sha256_fails_closed(tmp_path):
    payload = _release()
    payload.pop("sha256")
    service, calls = _service(tmp_path, payload=payload)
    assert service.check()["state"] == "error"
    assert service.start_install()["state"] == "error"
    assert calls["downloads"] == [] and calls["launch"] == []


def test_download_happy_path(tmp_path):
    asset = f"{app_update.FEED_ASSET_PREFIX}SubScript-Setup-0.2.0.exe"
    progress = []

    def handler(request):
        assert request.full_url == asset
        return _FakeResponse(b"MZ-setup", url=asset)

    dest = tmp_path / "SubScript-Setup-0.2.0.exe"
    app_update.download_asset(asset, dest, lambda d, t: progress.append((d, t)), opener=_FakeOpener(handler))
    assert dest.read_bytes() == b"MZ-setup"
    assert progress[-1][0] == len(b"MZ-setup")


def test_download_rejects_oversized_installer(tmp_path):
    asset = f"{app_update.FEED_ASSET_PREFIX}SubScript-Setup-0.2.0.exe"

    def handler(request):
        return _FakeResponse(b"12345", url=asset)

    dest = tmp_path / "SubScript-Setup-0.2.0.exe"
    with pytest.raises(app_update.UpdateError):
        app_update.download_asset(asset, dest, None, opener=_FakeOpener(handler), max_bytes=4)
    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))


def test_failed_download_does_not_launch_or_exit(tmp_path):
    def boom(url, dest, progress):
        raise app_update.Offline()

    service, calls = _service(tmp_path, download=boom)
    job = service.start_install()
    assert job["state"] == "error"
    assert job["message"] == "offline"
    assert calls["launch"] == []
    assert calls["shutdown"] == 0


def test_second_install_is_rejected_while_the_first_is_running(tmp_path):
    started = threading.Event()
    release = threading.Event()

    def download(url, dest, progress):
        started.set()
        assert release.wait(2)
        dest.write_bytes(b"MZ")

    service, _calls = _service(tmp_path, synchronous=False, download=download)
    service.start_install()
    assert started.wait(2)
    with pytest.raises(app_update.UpdateError, match="already"):
        service.start_install()
    release.set()
    service.worker.join(2)
    assert service.job()["state"] == "installing"


def test_launch_refuses_to_shell_out(monkeypatch, tmp_path):
    seen = {}

    def popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(app_update.subprocess, "Popen", popen)
    installer = tmp_path / "SubScript-Setup-0.2.0.exe"
    installer.write_bytes(b"MZ")
    app_update.default_launch(app_update.install_command(installer))
    assert seen["kwargs"].get("shell") in (None, False)
    assert seen["command"][1:] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    with pytest.raises(app_update.UpdateError):
        app_update.default_launch([str(installer), "/VERYSILENT", "calc.exe"])


def test_fetch_distinguishes_offline_from_no_releases():
    def missing(request):
        assert request.full_url == app_update.FEED_URL
        assert "Authorization" not in dict(request.header_items())
        raise _http_error(request.full_url, 404)

    with pytest.raises(app_update.NoReleases):
        app_update.default_fetch_json(app_update.FEED_URL, opener=_FakeOpener(missing))

    def down(request):
        raise urllib.error.URLError("no route")

    with pytest.raises(app_update.Offline):
        app_update.default_fetch_json(app_update.FEED_URL, opener=_FakeOpener(down))

    def blocked(request):
        raise AssertionError("should not request")

    with pytest.raises(app_update.UpdateError):
        app_update.default_fetch_json("https://example.com/latest.json", opener=_FakeOpener(blocked))


def test_updater_never_touches_user_data():
    source = (ROOT / "subscript" / "app_update.py").read_text(encoding="utf-8")
    assert "rmtree" not in source
    assert "config.yaml" not in source


def test_trailing_zero_segments_compare_equal():
    assert app_update.version_key(app_update.parse_version("0.7.1.0")) == app_update.version_key(app_update.parse_version("0.7.1"))
    assert app_update.version_key(app_update.parse_version("0.7.1.1")) > app_update.version_key(app_update.parse_version("0.7.1"))
    assert app_update.version_key(app_update.parse_version("0.7.0.1")) > app_update.version_key(app_update.parse_version("0.7.0"))


def test_feed_trailing_zero_is_not_an_update():
    sha = "a" * 64
    for latest, current in (("0.7.1.0", "0.7.1"), ("0.7.1", "0.7.1.0")):
        url = f"{app_update.FEED_ASSET_PREFIX}SubScript-Setup-{latest}.exe"
        out = app_update.interpret_feed({"version": latest, "url": url, "sha256": sha}, current, install_supported=True)
        assert out["update_available"] is False and out["state"] == "up_to_date"


def test_evaluate_unexpected_exception_is_user_facing_error():
    def broken(url):
        raise KeyError("surprise")

    svc = app_update.UpdateService(version="0.1.0", fetch_json=broken, frozen=True, platform_name="win32")
    out = svc.check()
    assert out["state"] == "error"
    assert out["message"] == "Could not check for updates. Try again later."
    assert out["update_available"] is False and out["can_install"] is False


def test_support_page_has_update_controls(app_env):
    page = app_env.client.get("/support")
    assert page.status_code == 200
    assert 'id="checkUpdate"' in page.text
    assert 'id="installUpdate"' in page.text
    assert 'id="updateStatus"' in page.text
    assert 'id="updateProgress"' in page.text
    assert "Check for updates" in page.text
    assert "Support & diagnostics" in page.text
    script = (ROOT / "subscript" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/update/status" in script
    assert "/update/install" in script
    assert "/update/job" in script


def test_sidebar_links_to_support_and_updates(app_env):
    page = app_env.client.get("/clip")
    assert page.status_code == 200
    assert 'href="/support"' in page.text
    assert "Support" in page.text


def test_api_check_and_source_install_block(app_env, tmp_path, monkeypatch):
    service, calls = _service(tmp_path, frozen=False)
    monkeypatch.setattr(app_update, "service", service)
    checked = app_env.client.get("/update/status")
    assert checked.status_code == 200
    body = checked.json()
    assert body["message"] == "version 0.2.0 available"
    assert body["can_install"] is False
    denied = app_env.client.post("/update/install")
    assert denied.status_code == 409
    assert "Windows app" in denied.json()["detail"]
    assert calls["launch"] == []


def test_api_install_reports_progress(app_env, tmp_path, monkeypatch):
    service, calls = _service(tmp_path)

    def download(url, dest, progress):
        progress(5, 10)
        dest.write_bytes(b"MZ")

    service.download = download
    monkeypatch.setattr(app_update, "service", service)
    started = app_env.client.post("/update/install")
    assert started.status_code == 200
    assert started.json()["state"] == "installing"
    job = app_env.client.get("/update/job")
    assert job.status_code == 200
    assert job.json()["completed"] == 5
    assert job.json()["total"] == 10
    assert calls["shutdown"] == 1
