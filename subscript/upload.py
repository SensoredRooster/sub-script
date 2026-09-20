"""YouTube Shorts upload + dry-run mock."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from subscript.config import ROOT
from subscript.config import load_dotenv as _load_dotenv

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
DEFAULT_SECRETS = "credentials.json"
DEFAULT_TOKEN = "token.json"


def _resolve_path(raw: str | None, default_name: str) -> Path:
    text = (raw or "").strip() or default_name
    path = Path(text)
    if not path.is_absolute():
        path = ROOT / path
    return path


def client_secrets_path(youtube_cfg: dict[str, Any] | None = None) -> Path:
    _load_dotenv()
    cfg = youtube_cfg or {}
    return _resolve_path(
        os.getenv("YOUTUBE_CLIENT_SECRETS")
        or cfg.get("client_secrets_file")
        or DEFAULT_SECRETS,
        DEFAULT_SECRETS,
    )


def token_path(youtube_cfg: dict[str, Any] | None = None) -> Path:
    _load_dotenv()
    cfg = youtube_cfg or {}
    return _resolve_path(
        os.getenv("YOUTUBE_TOKEN") or cfg.get("token_file") or DEFAULT_TOKEN,
        DEFAULT_TOKEN,
    )


def _ensure_shorts_description(description: str | None) -> str:
    text = (description or "").strip()
    if "#Shorts" not in text and "#shorts" not in text:
        text = f"{text}\n\n#Shorts".strip() if text else "#Shorts"
    return text


def dry_run_upload(video: Path, youtube_cfg: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Record what would be uploaded without calling YouTube."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = (youtube_cfg.get("title_template") or "Highlight {timestamp}").format(
        timestamp=stamp
    )
    payload = {
        "dry_run": True,
        "file": str(video),
        "title": title,
        "description": (_ensure_shorts_description(youtube_cfg.get("description")) if youtube_cfg.get("format", "vertical") == "vertical" else (youtube_cfg.get("description") or "")),
        "privacy": youtube_cfg.get("privacy", "unlisted"),
        "tags": youtube_cfg.get("tags") or [],
        "category_id": youtube_cfg.get("category_id", "20"),
        "note": "youtube.enabled is false — no live upload",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = out_dir / f"upload-dry-run-{stamp}.json"
    meta.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def get_youtube_credentials(youtube_cfg: dict[str, Any], *, timeout_seconds: int = 120) -> Any:
    """Load or create OAuth credentials (opens browser on first run)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets = client_secrets_path(youtube_cfg)
    token = token_path(youtube_cfg)

    if not secrets.is_file():
        raise RuntimeError(
            "YouTube client secrets file not found.\n"
            f"  Looked for: {secrets}\n"
            "  1) Create an OAuth Desktop client in Google Cloud Console\n"
            "     (APIs & Services → Credentials → Create OAuth client ID).\n"
            "  2) Enable YouTube Data API v3 for that project.\n"
            "  3) Download the JSON and save it as credentials.json in this folder\n"
            "     (or set youtube.client_secrets_file / YOUTUBE_CLIENT_SECRETS).\n"
            "  See README → Connect YouTube."
        )

    creds: Credentials | None = None
    if token.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(token), [YOUTUBE_UPLOAD_SCOPE])
        except Exception:  # noqa: BLE001
            creds = None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:  # noqa: BLE001
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secrets), [YOUTUBE_UPLOAD_SCOPE]
        )
        # Opens the system browser once; saves token for next Approves.
        creds = flow.run_local_server(port=0, prompt="consent", timeout_seconds=timeout_seconds)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json(), encoding="utf-8")

    return creds


def upload_youtube(video: Path, youtube_cfg: dict[str, Any]) -> dict[str, Any]:
    """Upload a vertical clip as a YouTube Short (OAuth + videos.insert)."""
    if not youtube_cfg.get("enabled"):
        raise RuntimeError("youtube.enabled is false — use dry-run or enable in config")

    video = Path(video)
    if not video.is_file():
        raise RuntimeError(f"Upload video missing: {video}")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_youtube_credentials(youtube_cfg)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    title = (youtube_cfg.get("title_template") or "Highlight {timestamp}").format(
        timestamp=stamp
    )
    # Keep titles Shorts-friendly (YouTube soft-caps ~100 chars).
    title = title[:100]
    description = (_ensure_shorts_description(youtube_cfg.get("description"))
                   if youtube_cfg.get("format", "vertical") == "vertical" else (youtube_cfg.get("description") or ""))
    privacy = (youtube_cfg.get("privacy") or "unlisted").lower().strip()
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "unlisted"
    tags = list(youtube_cfg.get("tags") or [])
    category_id = str(youtube_cfg.get("category_id") or "20")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response: dict[str, Any] | None = None
    while response is None:
        _status, response = request.next_chunk()

    video_id = (response or {}).get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload returned no video id: {response!r}")

    url = f"https://youtu.be/{video_id}"
    return {
        "dry_run": False,
        "file": str(video),
        "title": title,
        "description": description,
        "privacy": privacy,
        "tags": tags,
        "category_id": category_id,
        "id": video_id,
        "url": url,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        "shorts_url": f"https://www.youtube.com/shorts/{video_id}" if youtube_cfg.get("format", "vertical") == "vertical" else None,
    }
