"""TikTok Login Kit + Content Posting API publisher.

The desktop flow uses TikTok's loopback redirect and PKCE requirements. Videos
are uploaded from the local approved clip with FILE_UPLOAD, so the app never
needs to expose a local video file on the public web.
"""

from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import os
import secrets
import string
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from subscript.config import ROOT, load_dotenv
from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult
from subscript.publish.manual import manual_handoff

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API_BASE = "https://open.tiktokapis.com"
DEFAULT_TOKEN_FILE = "tiktok-token.json"
DEFAULT_REDIRECT_PATH = "/connections/tiktok/callback"
DEFAULT_SCOPE = "user.info.basic,video.publish"
UPLOAD_SCOPE = "video.upload"
PUBLISH_SCOPE = "video.publish"
CHUNK_SIZE = 10_000_000
_UNRESERVED = string.ascii_letters + string.digits + "-._~"

_PENDING_AUTH: dict[str, dict[str, str | float]] = {}


class TikTokAPIError(RuntimeError):
    """A safe, user-facing TikTok API error without token values."""

    def __init__(self, message: str, *, status: int | None = None, code: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _resolve_path(raw: str | None, default_name: str) -> Path:
    path = Path((raw or "").strip() or default_name)
    return path if path.is_absolute() else ROOT / path


def token_path(cfg: dict[str, Any] | None = None) -> Path:
    load_dotenv()
    item = cfg or {}
    return _resolve_path(os.getenv("TIKTOK_TOKEN") or item.get("token_file"), DEFAULT_TOKEN_FILE)


def client_key(cfg: dict[str, Any] | None = None) -> str:
    load_dotenv()
    item = cfg or {}
    return str(os.getenv("TIKTOK_CLIENT_KEY") or item.get("client_key") or "").strip()


def client_secret(cfg: dict[str, Any] | None = None) -> str:
    load_dotenv()
    item = cfg or {}
    return str(os.getenv("TIKTOK_CLIENT_SECRET") or item.get("client_secret") or "").strip()


def redirect_uri(cfg: dict[str, Any] | None = None) -> str:
    load_dotenv()
    item = cfg or {}
    configured = str(os.getenv("TIKTOK_REDIRECT_URI") or item.get("redirect_uri") or "").strip()
    if configured:
        return configured
    port = int((item.get("review") or {}).get("port") or 8787)
    return f"http://127.0.0.1:{port}{DEFAULT_REDIRECT_PATH}"


def connection_status(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return safe connection state for the UI; never expose secrets or paths."""
    key_ready = bool(client_key(cfg) and client_secret(cfg))
    token = token_path(cfg)
    data: dict[str, Any] = {}
    if token.is_file():
        try:
            raw = json.loads(token.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, ValueError):
            data = {}
    has_token = bool(data.get("access_token") and data.get("refresh_token"))
    if not key_ready:
        state = "setup"
        label = "Setup needed"
        detail = "Add the TikTok client key and secret to your local .env file, then restart SubScript."
    elif has_token:
        state = "connected"
        label = "Connected"
        detail = "TikTok authorization is saved on this computer."
    else:
        state = "disconnected"
        label = "Not connected"
        detail = "Connect TikTok once; SubScript will open TikTok in your browser."
    return {"state": state, "label": label, "detail": detail, "configured": key_ready, "connected": has_token, "redirect_uri": redirect_uri(cfg)}


def _random_verifier(length: int = 64) -> str:
    return "".join(secrets.choice(_UNRESERVED) for _ in range(length))


def _challenge(verifier: str) -> str:
    # TikTok's desktop documentation specifies hex-encoded SHA-256 for S256.
    return hashlib.sha256(verifier.encode("ascii")).hexdigest()


def begin_authorization(cfg: dict[str, Any]) -> str:
    """Create a short-lived PKCE request and return TikTok's authorize URL."""
    if not client_key(cfg) or not client_secret(cfg):
        raise NotConfiguredError("TikTok is not configured yet. Add TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET to .env, then restart SubScript.")
    verifier = _random_verifier()
    state = secrets.token_urlsafe(32)
    mode = str(cfg.get("mode") or "api").strip().lower()
    scope = str(cfg.get("scope") or (UPLOAD_SCOPE if mode == "upload" else DEFAULT_SCOPE)).strip()
    _PENDING_AUTH[state] = {"verifier": verifier, "redirect_uri": redirect_uri(cfg), "created_at": time.time()}
    cutoff = time.time() - 600
    for old_state, item in list(_PENDING_AUTH.items()):
        if float(item.get("created_at", 0)) < cutoff:
            _PENDING_AUTH.pop(old_state, None)
    query = urllib.parse.urlencode({
        "client_key": client_key(cfg), "response_type": "code", "scope": scope,
        "redirect_uri": redirect_uri(cfg), "state": state,
        "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
    })
    return f"{AUTHORIZE_URL}?{query}"


def _json_response(response: Any) -> dict[str, Any]:
    try:
        payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise TikTokAPIError("TikTok returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise TikTokAPIError("TikTok returned an unexpected response.")
    return payload


def _safe_api_error(payload: dict[str, Any], status: int | None = None) -> TikTokAPIError:
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "")
        message = str(error.get("message") or "TikTok rejected the request.")
        log_id = str(error.get("log_id") or "")
    else:
        code = str(payload.get("error") or "")
        message = str(payload.get("error_description") or "TikTok rejected the request.")
        log_id = str(payload.get("log_id") or "")
    suffix = f" (code: {code})" if code else ""
    if log_id:
        suffix += f" Log ID: {log_id}."
    return TikTokAPIError(f"{message}{suffix}", status=status, code=code)


def _request_json(method: str, url: str, *, form: dict[str, str] | None = None, body: dict[str, Any] | None = None, access_token: str | None = None, timeout: int = 60) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=UTF-8"
    else:
        data = None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = _json_response(response)
    except urllib.error.HTTPError as exc:
        try:
            payload = _json_response(exc)
        except TikTokAPIError:
            raise TikTokAPIError(f"TikTok request failed with HTTP {exc.code}.", status=exc.code) from exc
        raise _safe_api_error(payload, exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TikTokAPIError("Could not reach TikTok. Check your internet connection and try again.") from exc
    error = payload.get("error")
    if isinstance(error, dict) and str(error.get("code") or "ok") != "ok":
        raise _safe_api_error(payload)
    return payload


def _save_token(data: dict[str, Any], cfg: dict[str, Any]) -> None:
    path = token_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def finish_authorization(cfg: dict[str, Any], *, code: str, state: str) -> None:
    pending = _PENDING_AUTH.pop(state, None)
    if not pending or time.time() - float(pending.get("created_at", 0)) > 600:
        raise TikTokAPIError("TikTok sign-in expired. Start Connect TikTok again.")
    if str(pending.get("redirect_uri")) != redirect_uri(cfg):
        raise TikTokAPIError("TikTok redirect settings changed. Start Connect TikTok again.")
    payload = _request_json("POST", TOKEN_URL, form={
        "client_key": client_key(cfg), "client_secret": client_secret(cfg), "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri(cfg),
        "code_verifier": str(pending["verifier"]),
    })
    if payload.get("error"):
        raise _safe_api_error(payload)
    data = dict(payload)
    now = int(time.time())
    data["obtained_at"] = now
    data["expires_at"] = now + int(data.get("expires_in") or 86400)
    data["refresh_expires_at"] = now + int(data.get("refresh_expires_in") or 31_536_000)
    _save_token(data, cfg)


def _load_token(cfg: dict[str, Any]) -> dict[str, Any]:
    path = token_path(cfg)
    if not path.is_file():
        raise NotConfiguredError("Connect TikTok before publishing. Click Connect TikTok in the TikTok destination card.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NotConfiguredError("The saved TikTok connection is unreadable. Disconnect and connect TikTok again.") from exc
    if not isinstance(data, dict) or not data.get("access_token"):
        raise NotConfiguredError("Connect TikTok before publishing. The saved authorization is incomplete.")
    return data


def access_token(cfg: dict[str, Any], required_scope: str) -> str:
    data = _load_token(cfg)
    now = int(time.time())
    if int(data.get("expires_at") or 0) <= now + 60:
        refresh = str(data.get("refresh_token") or "")
        if not refresh:
            raise NotConfiguredError("TikTok authorization expired. Click Reconnect TikTok and finish sign-in again.")
        payload = _request_json("POST", TOKEN_URL, form={
            "client_key": client_key(cfg), "client_secret": client_secret(cfg),
            "grant_type": "refresh_token", "refresh_token": refresh,
        })
        updated = dict(data)
        updated.update(payload)
        updated["obtained_at"] = now
        updated["expires_at"] = now + int(payload.get("expires_in") or 86400)
        if payload.get("refresh_expires_in"):
            updated["refresh_expires_at"] = now + int(payload["refresh_expires_in"])
        _save_token(updated, cfg)
        data = updated
    granted = {part.strip() for part in str(data.get("scope") or "").split(",") if part.strip()}
    if required_scope not in granted:
        raise NotConfiguredError(f"TikTok authorization is missing the {required_scope} permission. Reconnect after TikTok approves that scope.")
    return str(data["access_token"])


def _caption(meta: PublishMeta) -> str:
    lines = [str(meta.title or "").strip(), str(meta.description or "").strip()]
    existing = " ".join(lines)
    tags = []
    for tag in meta.tags or []:
        clean = str(tag).strip().lstrip("#")
        if clean and f"#{clean}" not in existing:
            tags.append(f"#{clean}")
    if tags:
        lines.append(" ".join(tags))
    return "\n".join(line for line in lines if line)[:2200]


def _upload_file(upload_url: str, path: Path, size: int) -> None:
    total = max(1, math.ceil(size / CHUNK_SIZE))
    content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    with path.open("rb") as source:
        for index in range(total):
            start = index * CHUNK_SIZE
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            end = start + len(chunk) - 1
            request = urllib.request.Request(upload_url, data=chunk, headers={
                "Content-Type": content_type, "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }, method="PUT")
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    if response.status not in {200, 201, 206}:
                        raise TikTokAPIError(f"TikTok rejected video upload with HTTP {response.status}.")
            except urllib.error.HTTPError as exc:
                raise TikTokAPIError(f"TikTok rejected video upload with HTTP {exc.code}.", status=exc.code) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise TikTokAPIError("The video upload was interrupted. Check your connection and try again.") from exc


def _status(cfg: dict[str, Any], publish_id: str, scope: str) -> dict[str, Any]:
    token = access_token(cfg, scope)
    payload = _request_json("POST", f"{API_BASE}/v2/post/publish/status/fetch/", body={"publish_id": publish_id}, access_token=token)
    return dict(payload.get("data") or {})


class TikTokClient:
    """Small API client kept separate so publisher and route tests stay simple."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg

    def creator_info(self, token: str) -> dict[str, Any]:
        payload = _request_json("POST", f"{API_BASE}/v2/post/publish/creator_info/query/", body={}, access_token=token)
        return dict(payload.get("data") or {})

    def publish_video(self, path: Path, meta: PublishMeta) -> PublishResult:
        path = Path(path)
        if not path.is_file():
            return PublishResult(platform="TikTok", ok=False, status="error", message="TikTok video is missing. Rebuild the clip and try again.")
        size = path.stat().st_size
        if size <= 0:
            return PublishResult(platform="TikTok", ok=False, status="error", message="TikTok cannot upload an empty video file.")
        if size > 4 * 1024 * 1024 * 1024:
            return PublishResult(platform="TikTok", ok=False, status="error", message="TikTok videos must be 4 GB or smaller.")
        mode = str(self.cfg.get("mode") or "api").strip().lower()
        scope = UPLOAD_SCOPE if mode == "upload" else PUBLISH_SCOPE
        token = access_token(self.cfg, scope)
        chunk_count = max(1, math.ceil(size / CHUNK_SIZE))
        source_info = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": CHUNK_SIZE, "total_chunk_count": chunk_count}
        if mode == "upload":
            endpoint = "/v2/post/publish/inbox/video/init/"
            body = {"source_info": source_info}
        else:
            creator = self.creator_info(token)
            options = [str(item) for item in creator.get("privacy_level_options") or []]
            privacy = str(self.cfg.get("privacy_level") or "SELF_ONLY").strip().upper()
            if options and privacy not in options:
                return PublishResult(platform="TikTok", ok=False, status="error", message="TikTok does not allow the saved privacy setting for this account. Refresh creator settings and try again.", detail={"privacy_options": options})
            if not options:
                privacy = "SELF_ONLY"
            endpoint = "/v2/post/publish/video/init/"
            body = {"post_info": {
                "title": _caption(meta), "privacy_level": privacy,
                "disable_duet": bool(self.cfg.get("disable_duet", False)),
                "disable_comment": bool(self.cfg.get("disable_comment", False)),
                "disable_stitch": bool(self.cfg.get("disable_stitch", False)),
                "brand_content_toggle": bool(self.cfg.get("brand_content_toggle", False)),
                "brand_organic_toggle": bool(self.cfg.get("brand_organic_toggle", False)),
                "is_aigc": bool(self.cfg.get("is_aigc", False)),
            }, "source_info": source_info}
        initialized = _request_json("POST", f"{API_BASE}{endpoint}", body=body, access_token=token)
        data = dict(initialized.get("data") or {})
        publish_id = str(data.get("publish_id") or "")
        upload_url = str(data.get("upload_url") or "")
        if not publish_id or not upload_url:
            raise TikTokAPIError("TikTok did not provide an upload destination. Try again.")
        _upload_file(upload_url, path, size)
        latest: dict[str, Any] = {}
        for _ in range(3):
            time.sleep(1)
            latest = _status(self.cfg, publish_id, scope)
            if str(latest.get("status") or "").upper() in {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"}:
                break
        state = str(latest.get("status") or "PROCESSING_UPLOAD").upper()
        if state == "FAILED":
            reason = str(latest.get("fail_reason") or "TikTok could not process this video.").replace("_", " ")
            return PublishResult(platform="TikTok", ok=False, status="error", message=reason.capitalize(), detail={"publish_id": publish_id, **latest})
        if mode == "upload" or state == "SEND_TO_USER_INBOX":
            return PublishResult(platform="TikTok", ok=True, status="submitted", message="Draft sent to TikTok. Open TikTok to finish editing and post it.", detail={"publish_id": publish_id, **latest})
        if state == "PUBLISH_COMPLETE":
            return PublishResult(platform="TikTok", ok=True, status="uploaded", message="TikTok post published.", detail={"publish_id": publish_id, **latest})
        return PublishResult(platform="TikTok", ok=True, status="submitted", message="TikTok accepted the video and is still processing it.", detail={"publish_id": publish_id, **latest})


class TikTokPublisher:
    name = "tiktok"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._plat = dict((cfg.get("platforms") or {}).get("tiktok") or {})

    @property
    def enabled(self) -> bool:
        return bool(self._plat.get("enabled"))

    def publish(self, path: Path, meta: PublishMeta) -> PublishResult:
        mode = str(self._plat.get("mode") or "manual").lower().strip()
        if mode in {"api", "direct", "upload"}:
            return TikTokClient(self._plat).publish_video(path, meta)
        return manual_handoff(
            platform_key="tiktok", display_name="TikTok", path=path, meta=meta,
            instructions=(
                "TikTok — manual post steps\n==========================\n"
                "1. Open TikTok Studio or the TikTok app.\n"
                "2. Upload vertical_captioned.mp4 from this folder.\n"
                "3. Copy the caption and hashtags from POST_COPY.txt.\n"
                "4. Review the video, then post or save it as a draft."
            ),
        )
