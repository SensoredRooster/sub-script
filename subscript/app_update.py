"""Check for a newer Windows Setup build and install it.

The only update source is the SubScript feed on Cloudflare:
``https://subscript-updates.sensoredrooster-com.workers.dev/latest.json``
plus ``releases/<Setup>.exe`` on the same host. Only HTTPS is accepted, redirects
are never followed, and the download must match the sha256 in ``latest.json``
before it is run. Anything else fails closed with a clear error. User data
(config, clips, tokens) is never referenced here; the installer only replaces
the application directory.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from subscript import __version__ as APP_VERSION

FEED_HOST = "subscript-updates.sensoredrooster-com.workers.dev"
FEED_URL = f"https://{FEED_HOST}/latest.json"
FEED_ASSET_PREFIX = f"https://{FEED_HOST}/releases/"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
INNO_SILENT_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024 * 1024
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?(?:-[A-Za-z0-9.]+)?$", re.IGNORECASE)
_USER_AGENT = f"SubScript/{APP_VERSION}"


class UpdateError(Exception):
    pass


class Offline(UpdateError):
    pass


class NoReleases(UpdateError):
    pass


def parse_version(value: str):
    match = _VERSION.fullmatch(str(value).strip())
    if not match:
        raise UpdateError("Unrecognized version.")
    return tuple(int(part) for part in match.groups() if part is not None)


def version_key(parts) -> tuple:
    """Comparison key that ignores trailing zero segments, so 0.7.1.0 == 0.7.1."""
    parts = tuple(parts)
    while len(parts) > 3 and parts[-1] == 0:
        parts = parts[:-1]
    return parts


def format_version(parts) -> str:
    return ".".join(str(part) for part in parts)


SETUP_PREFIXES = ("SubScript-Setup-",)


def setup_filename(version: str, prefix: str = SETUP_PREFIXES[0]) -> str:
    if prefix not in SETUP_PREFIXES:
        raise UpdateError("Unrecognized installer name.")
    return f"{prefix}{format_version(parse_version(version))}.exe"


def is_setup_filename(name: str, version: str = None) -> bool:
    for prefix in SETUP_PREFIXES:
        if not isinstance(name, str) or not name.startswith(prefix) or not name.endswith(".exe"):
            continue
        middle = name[len(prefix):-len(".exe")]
        try:
            if name == setup_filename(middle, prefix) and (
                version is None or parse_version(middle) == parse_version(version)
            ):
                return True
        except UpdateError:
            return False
    return False


def _https_parts(url: str):
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UpdateError("Update URLs must use HTTPS.")
    if parts.username or parts.password or parts.port not in (None, 443) or not parts.hostname:
        raise UpdateError("Update URL is not a SubScript release.")
    return parts


def is_feed_asset_url(url: str) -> bool:
    try:
        parts = _https_parts(url)
    except UpdateError:
        return False
    if parts.hostname.lower() != FEED_HOST or parts.query or parts.fragment:
        return False
    if not parts.path.startswith("/releases/"):
        return False
    name = parts.path[len("/releases/"):]
    return bool(name) and "/" not in name and is_setup_filename(name)


def require_feed_asset_url(url: str) -> str:
    """Fail closed unless url is an HTTPS Setup installer on the Cloudflare feed host."""
    if not isinstance(url, str):
        raise UpdateError("Update URL is not a SubScript release.")
    _https_parts(url)
    if not is_feed_asset_url(url):
        raise UpdateError("Update URL is not a SubScript release.")
    return url


def install_command(installer: Path) -> list[str]:
    path = Path(installer)
    if not is_setup_filename(path.name):
        raise UpdateError("Refusing to run an unexpected installer.")
    return [str(path), *INNO_SILENT_ARGS]


def default_launch(command: list[str]) -> None:
    if list(command[1:]) != INNO_SILENT_ARGS:
        raise UpdateError("Refusing to run an unexpected installer.")
    install_command(Path(command[0]))
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    subprocess.Popen(command, **kwargs)


def schedule_exit(delay: float = 0.8) -> None:
    def _exit():
        time.sleep(delay)
        os._exit(0)
    threading.Thread(target=_exit, daemon=False, name="subscript-update-exit").start()


def _blank(current: str, **extra) -> dict:
    body = {
        "state": "error",
        "message": "Could not read the latest release.",
        "current": current,
        "latest": None,
        "update_available": False,
        "install_supported": False,
        "can_install": False,
        "asset_name": None,
        "asset_url": None,
        "detail": "",
    }
    body.update(extra)
    return body


def interpret_feed(payload, current: str, *, install_supported: bool) -> dict:
    """Read latest.json: {"version", "url", "sha256", "notes"}. Raises UpdateError when unusable."""
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
        raise UpdateError("Update feed is malformed.")
    parts = parse_version(payload["version"])
    dotted = format_version(parts)
    url = payload.get("url")
    sha = payload.get("sha256")
    if not isinstance(url, str):
        raise UpdateError("Update feed link is not a SubScript release.")
    require_feed_asset_url(url)
    name = url[len(FEED_ASSET_PREFIX):]
    if not is_setup_filename(name, dotted):
        raise UpdateError("Update feed link is not the Setup installer.")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha.lower()):
        raise UpdateError("Update feed has no valid sha256.")
    current_parts = parse_version(current)
    newer = version_key(parts) > version_key(current_parts)
    notes = payload.get("notes")
    return {
        "state": "available" if newer else "up_to_date",
        "message": f"version {dotted} available" if newer else f"You're up to date ({format_version(current_parts)})",
        "current": format_version(current_parts),
        "latest": dotted,
        "update_available": newer,
        "install_supported": install_supported,
        "can_install": bool(install_supported and newer),
        "asset_name": name,
        "asset_url": url,
        "sha256": sha.lower(),
        "notes": notes if isinstance(notes, str) else "",
        "source": "feed",
        "detail": "",
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Update URLs are exact; a redirect means something is wrong, so refuse it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_opener():
    return urllib.request.build_opener(_NoRedirectHandler())


def default_fetch_json(url: str, *, opener=None) -> dict:
    if url != FEED_URL:
        raise UpdateError("Update check only reads the SubScript update feed.")
    _https_parts(url)
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": _USER_AGENT}
    )
    try:
        with (opener or _default_opener()).open(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            raw = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            raise UpdateError("Update feed redirect was rejected.") from exc
        if exc.code == 404:
            raise NoReleases() from exc
        raise UpdateError("Could not read the update feed.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Offline() from exc
    if status != 200:
        raise UpdateError("Could not read the update feed.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError("Could not read the update feed.") from exc
    if not isinstance(data, dict):
        raise UpdateError("Could not read the update feed.")
    return data


def download_asset(asset_url: str, dest: Path, progress, *, opener=None, max_bytes: int = MAX_DOWNLOAD_BYTES) -> None:
    url = require_feed_asset_url(asset_url)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/octet-stream"}
    )
    try:
        with (opener or _default_opener()).open(request, timeout=120) as response:
            status = getattr(response, "status", 200)
            if status != 200 or response.geturl() != url:
                raise UpdateError("Could not download the update.")
            total_header = response.headers.get("content-length") if response.headers else None
            total = int(total_header) if total_header and str(total_header).isdigit() else 0
            if total > max_bytes:
                raise UpdateError("Update installer is too large.")
            done = 0
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > max_bytes:
                        raise UpdateError("Update installer is too large.")
                    handle.write(chunk)
                    if progress:
                        progress(done, total)
            if done == 0:
                raise UpdateError("Update installer was empty.")
            partial.replace(dest)
    except urllib.error.HTTPError as exc:
        partial.unlink(missing_ok=True)
        if 300 <= exc.code < 400:
            raise UpdateError("Update download redirect was rejected.") from exc
        raise UpdateError("Could not download the update.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise Offline() from exc
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _public(status: dict) -> dict:
    return {key: value for key, value in status.items() if key != "asset_url"}


class UpdateService:
    def __init__(self, *, version=APP_VERSION, frozen=None, platform_name=None, fetch_json=None,
                 download=None, launch=None, shutdown=None, synchronous=False, temp_factory=None):
        self.version = version
        self.frozen = bool(getattr(sys, "frozen", False) if frozen is None else frozen)
        self.platform_name = platform_name or sys.platform
        self.fetch_json = fetch_json or default_fetch_json
        self.download = download or download_asset
        self.launch = launch or default_launch
        self.shutdown = shutdown or schedule_exit
        self.synchronous = synchronous
        self.temp_factory = temp_factory or (lambda: Path(tempfile.mkdtemp(prefix="subscript-update-")))
        self._lock = threading.Lock()
        self._job = {"state": "idle", "message": "Ready", "completed": 0, "total": 0}
        self._status = None
        self.worker = None

    @property
    def install_supported(self) -> bool:
        return self.frozen and self.platform_name == "win32"

    def _set(self, **values) -> None:
        with self._lock:
            self._job.update(values)

    def job(self) -> dict:
        with self._lock:
            return dict(self._job)

    def _evaluate(self) -> dict:
        try:
            return self._evaluate_inner()
        except Exception as exc:  # never let a surprise break the update check
            return _blank(self.version, message="Could not check for updates. Try again later.",
                          detail=type(exc).__name__, install_supported=self.install_supported)

    def _evaluate_inner(self) -> dict:
        supported = self.install_supported
        try:
            payload = self.fetch_json(FEED_URL)
        except NoReleases:
            return _blank(self.version, state="no_releases", message="no releases", install_supported=supported)
        except Offline:
            return _blank(self.version, state="offline", message="offline", install_supported=supported)
        except UpdateError as exc:
            return _blank(self.version, message=str(exc), install_supported=supported)
        except (TimeoutError, OSError):
            return _blank(self.version, state="offline", message="offline", install_supported=supported)
        try:
            return interpret_feed(payload, self.version, install_supported=supported)
        except UpdateError as exc:
            return _blank(self.version, message=str(exc), install_supported=supported)

    def check(self) -> dict:
        self._status = self._evaluate()
        return _public(self._status)

    def start_install(self) -> dict:
        if not self.install_supported:
            raise UpdateError("Install updates from the Windows app.")
        with self._lock:
            if self._job["state"] in {"downloading", "installing"}:
                raise UpdateError("An update is already running.")
        status = self.check()
        if status["state"] == "up_to_date":
            raise UpdateError(status["message"])
        if not status["can_install"]:
            self._set(state="error", message=status["detail"] or status["message"], completed=0, total=0)
            return self.job()
        self._set(state="downloading", message=f"Downloading version {status['latest']}", completed=0, total=0)
        self.worker = threading.Thread(target=self._install, name="subscript-update")
        self.worker.start()
        if self.synchronous:
            self.worker.join()
        return self.job()

    def _install(self) -> None:
        status = self._status or {}
        try:
            latest = status["latest"]
            filename = status["asset_name"]
            if not filename or Path(filename).name != filename:
                raise UpdateError("Refusing to run an unexpected installer.")
            directory = Path(self.temp_factory())
            dest = directory / filename
            if dest.parent.resolve() != directory.resolve():
                raise UpdateError("Refusing to run an unexpected installer.")
            require_feed_asset_url(status["asset_url"])
            expected = status.get("sha256")
            if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
                raise UpdateError("Update has no valid sha256; refusing to install.")

            def progress(done, total):
                self._set(state="downloading", message=f"Downloading version {latest}", completed=done, total=total)

            self.download(status["asset_url"], dest, progress)
            if not dest.is_file() or dest.stat().st_size <= 0:
                raise UpdateError("Could not download the update.")
            digest = hashlib.sha256()
            with dest.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                dest.unlink(missing_ok=True)
                raise UpdateError("Update installer failed its checksum.")
            self._set(state="installing", message=f"Installing version {latest}. SubScript will close and reopen.")
            self.launch(install_command(dest))
            if self.shutdown:
                self.shutdown()
        except NoReleases:
            self._set(state="error", message="no releases")
        except Offline:
            self._set(state="error", message="offline")
        except UpdateError as exc:
            self._set(state="error", message=str(exc))
        except Exception:
            self._set(state="error", message="Update failed.")


service = UpdateService()
