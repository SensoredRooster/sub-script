"""User-facing publishing settings panel and routes."""

from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import Any
from urllib.parse import quote
import webbrowser

from fastapi import FastAPI, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from subscript.post_metadata import generate_posts, PLATFORMS
from subscript.output_formats import FORMATS, selected_format

from subscript.config import dry_run_forced, save_config
from subscript.upload import client_secrets_path, token_path, get_youtube_credentials
from subscript.publish.tiktok import (
    TikTokAPIError,
    begin_authorization,
    connection_status as tiktok_connection_status,
    finish_authorization,
)
from subscript.publish.base import NotConfiguredError


def youtube_connection_status(cfg):
    youtube = cfg.get("youtube") or {}
    configured = client_secrets_path(youtube).is_file()
    exists = token_path(youtube).is_file()
    usable = False
    try:
        from google.oauth2.credentials import Credentials
        from subscript.upload import YOUTUBE_UPLOAD_SCOPE
        creds = Credentials.from_authorized_user_file(str(token_path(youtube)), [YOUTUBE_UPLOAD_SCOPE])
        usable = bool(creds.valid or creds.refresh_token)
    except Exception:
        pass
    state = "connected" if usable else "attention" if exists else "disconnected"
    if not configured:
        state = "attention"
    status = {"connected": "Connected", "attention": "Needs attention", "disconnected": "Not connected"}[state]
    detail = ("Google authorization is saved on this computer."
              if state == "connected" else "Sign in with Google to connect your channel."
              if state == "disconnected" else "Your saved authorization needs to be renewed."
              if configured else "YouTube connection setup is missing on this installation.")
    enabled = bool(youtube.get("enabled") or ((cfg.get("platforms") or {}).get("youtube") or {}).get("enabled"))
    delivery = "Uploads paused · preview mode" if dry_run_forced() else "Uploads enabled" if enabled else "Uploads off"
    return {"state": state, "label": status, "detail": detail, "delivery": delivery, "configured": configured}


def youtube_connection_html(cfg):
    status = youtube_connection_status(cfg)
    label = "Reconnect YouTube" if status["state"] == "attention" else "Connect YouTube"
    button = "" if status["state"] == "connected" else f'<button type="submit" form="youtube-connect-form" {"" if status["configured"] else "disabled"}>{label}</button>'
    return (f'<div class="connection-panel connection-{status["state"]}" aria-label="YouTube connection">'
            '<div class="connection-summary">'
            f'<span class="connection-badge"><span aria-hidden="true">●</span> {status["label"]}</span>'
            f'<span class="connection-delivery">{status["delivery"]}</span></div>'
            f'<p class="meta">{status["detail"]}</p>'
            f'{button}'
            '<p class="meta">Connection and publishing are separate. Your account can stay connected while uploads are off. Saved authorization is checked locally; Google may require sign-in again when uploading.</p></div>')


def tiktok_connection_html(cfg):
    tiktok_cfg = dict((cfg.get("platforms") or {}).get("tiktok") or {})
    tiktok_cfg["review"] = dict(cfg.get("review") or {})
    status = tiktok_connection_status(tiktok_cfg)
    label = "Reconnect TikTok" if status["state"] == "connected" else "Connect TikTok"
    disabled = "" if status["configured"] else "disabled"
    setup = (
        '<p class="meta">Set <code>TIKTOK_CLIENT_KEY</code> and <code>TIKTOK_CLIENT_SECRET</code> in the local <code>.env</code> file. '
        f'Register this exact redirect URI in TikTok: <code>{escape(status["redirect_uri"])}</code></p>'
        if not status["configured"] else ""
    )
    button = f'<button type="submit" form="tiktok-connect-form" {disabled}>{label}</button>'
    return (
        f'<div class="connection-panel connection-{status["state"]}" aria-label="TikTok connection">'
        '<div class="connection-summary">'
        f'<span class="connection-badge"><span aria-hidden="true">●</span> {escape(status["label"])}</span>'
        '<span class="connection-delivery">Direct posting is off until enabled</span></div>'
        f'<p class="meta">{escape(status["detail"])}</p>{setup}{button}'
        '<p class="meta">Manual upload packs still work without an account connection. Direct posting requires TikTok approval for the selected permission.</p></div>'
    )

_MANUAL_PLATFORMS = (
    ("tiktok", "TikTok", "Vertical video + posting instructions"),
    ("instagram", "Instagram", "Reels-ready vertical pack"),
    ("facebook", "Facebook", "Reels-ready vertical pack"),
    ("twitter", "X / Twitter", "Social-ready video pack"),
    ("rumble", "Rumble", "Upload-ready video pack"),
)


def _checked(value: Any) -> str:
    return "checked" if bool(value) else ""


def _selected(value: str, expected: str) -> str:
    return "selected" if value == expected else ""


def _platform_tags(value: Any) -> str:
    raw = value or []
    if isinstance(raw, str):
        return raw
    return ", ".join(str(tag) for tag in raw)


def publishing_html(cfg: dict[str, Any], snip: Callable[[str], str]) -> str:
    """Render discoverable platform controls from the active configuration."""
    youtube = dict(cfg.get("youtube") or {})
    platforms = dict(cfg.get("platforms") or {})
    yt_platform = dict(platforms.get("youtube") or {})
    yt_enabled = bool(youtube.get("enabled") or yt_platform.get("enabled"))
    privacy = str(youtube.get("privacy") or "unlisted").lower()
    tags = youtube.get("tags") or []
    if isinstance(tags, str):
        tag_text = tags
    else:
        tag_text = ", ".join(str(tag) for tag in tags)

    cards: list[str] = []
    for key, name, detail in _MANUAL_PLATFORMS:
        item = dict(platforms.get(key) or {})
        title = escape(str(item.get("title_template") or ""), quote=True)
        description = escape(str(item.get("description") or ""))
        tags = escape(_platform_tags(item.get("tags")), quote=True)
        tiktok_controls = (
            tiktok_connection_html(cfg)
            + '<label>Delivery<select name="tiktok_mode">'
            f'<option value="manual" {_selected(str(item.get("mode") or "manual"), "manual")}>Local upload pack</option>'
            f'<option value="api" {_selected(str(item.get("mode") or "manual"), "api")}>Direct post to TikTok</option>'
            f'<option value="upload" {_selected(str(item.get("mode") or "manual"), "upload")}>Send to TikTok drafts</option>'
            '</select></label>'
            '<label>Privacy for direct posts<select name="tiktok_privacy">'
            f'<option value="SELF_ONLY" {_selected(str(item.get("privacy_level") or "SELF_ONLY"), "SELF_ONLY")}>Private (recommended for testing)</option>'
            f'<option value="MUTUAL_FOLLOW_FRIENDS" {_selected(str(item.get("privacy_level") or ""), "MUTUAL_FOLLOW_FRIENDS")}>Friends</option>'
            f'<option value="FOLLOWER_OF_CREATOR" {_selected(str(item.get("privacy_level") or ""), "FOLLOWER_OF_CREATOR")}>Followers</option>'
            f'<option value="PUBLIC_TO_EVERYONE" {_selected(str(item.get("privacy_level") or ""), "PUBLIC_TO_EVERYONE")}>Everyone</option>'
            '</select></label>'
            if key == "tiktok" else ""
        )
        delivery_note = (
            "Choose Local upload pack for tonight, or Direct post after TikTok approves video.publish."
            if key == "tiktok" else "These defaults are used for new clip drafts. Upload-ready packs are created locally. No account connection is needed in SubScript."
        )
        card_prefix = (
            f'<div class="platform-settings" {"" if item.get("enabled") else "hidden"}>{tiktok_controls}'
            if key == "tiktok" else
            f'<div class="platform-settings" {"" if item.get("enabled") else "hidden"}><input type="hidden" name="{key}_mode" value="manual">'
        )
        cards.append(
            f'<article class="platform-card" data-platform="{key}">'
            '<div class="platform-card-head">'
            f'<span class="platform-mark platform-{key}">{escape(name[:1])}</span>'
            f"<div><h3>{escape(name)}</h3><p>{escape(detail)}</p></div>"
            '<label class="switch" aria-label="Enable '
            f'{escape(name)}"><input type="checkbox" name="{key}_enabled" value="1" '
            f"{_checked(item.get('enabled'))}><span></span></label></div>"
            f'{card_prefix}'
        )
        cards[-1] += (
            f'<label>Output format<select name="{key}_format">' + ''.join(
                f'<option value="{value}" {_selected(selected_format(cfg, key), value)}>{label}</option>'
                for value, label in FORMATS[key].items()) + '</select></label>'
            f'<label>Default post title / caption <span class="field-hint">optional</span><input name="{key}_title" type="text" maxlength="95" value="{title}" placeholder="Leave blank for automatic copy"></label>'
            f'<label>Default description <span class="field-hint">optional</span><textarea name="{key}_description" rows="3" maxlength="1800">{description}</textarea></label>'
            f'<label>Default tags <span class="field-hint">comma separated</span><input name="{key}_tags" type="text" value="{tags}" placeholder="gaming, highlights"></label>'
            f'<p class="meta">{delivery_note}</p></div></article>'
        )

    return (
        snip("publishing.html")
        .replace("{{YT_CONNECTION}}", youtube_connection_html(cfg))
        .replace("{{COPY_ENABLED}}", _checked((cfg.get("post_copy") or {}).get("enabled", True)))
        .replace("{{COPY_GAME}}", escape(str((cfg.get("post_copy") or {}).get("game") or ""), quote=True))
        .replace("{{COPY_CREATOR}}", escape(str((cfg.get("post_copy") or {}).get("creator") or ""), quote=True))
        .replace("{{TONE_CASUAL}}", _selected((cfg.get("post_copy") or {}).get("tone", "casual"), "casual"))
        .replace("{{TONE_DIRECT}}", _selected((cfg.get("post_copy") or {}).get("tone", "casual"), "direct"))
        .replace("{{TONE_PLAYFUL}}", _selected((cfg.get("post_copy") or {}).get("tone", "casual"), "playful"))
        .replace("{{YT_ENABLED}}", _checked(yt_enabled))
        .replace("{{YT_SETTINGS_HIDDEN}}", "" if yt_enabled else "hidden")
        .replace("{{YT_FORMAT_VERTICAL}}", _selected(selected_format(cfg, "youtube"), "vertical"))
        .replace("{{YT_FORMAT_HORIZONTAL}}", _selected(selected_format(cfg, "youtube"), "horizontal"))
        .replace("{{REVIEW_SELECTED}}", _selected("review" if (cfg.get("review") or {}).get("require_approval", True) else "automatic", "review"))
        .replace("{{AUTO_SELECTED}}", _selected("review" if (cfg.get("review") or {}).get("require_approval", True) else "automatic", "automatic"))
        .replace(
            "{{YT_DRY_RUN}}",
            ""
            if not dry_run_forced()
            else (
                '<p class="inline-alert">Preview mode is active on this installation. Live uploads are disabled.</p>'
            ),
        )
        .replace("{{PRIV_PRIVATE}}", _selected(privacy, "private"))
        .replace("{{PRIV_UNLISTED}}", _selected(privacy, "unlisted"))
        .replace("{{PRIV_PUBLIC}}", _selected(privacy, "public"))
        .replace(
            "{{YT_TITLE}}",
            escape(
                str(youtube.get("title_template") or "Highlight {timestamp}"),
                quote=True,
            ),
        )
        .replace("{{YT_DESCRIPTION}}", escape(str(youtube.get("description") or "")))
        .replace("{{YT_TAGS}}", escape(tag_text, quote=True))
        .replace(
            "{{YT_CATEGORY}}",
            escape(str(youtube.get("category_id") or "20"), quote=True),
        )
        .replace("{{PLATFORM_CARDS}}", "\n".join(cards))
    )


def register_publishing_routes(app: FastAPI, cfg: dict[str, Any]) -> None:
    @app.post("/post-copy/preview")
    def preview_post_copy(copy_game: str = Form(""), copy_creator: str = Form(""),
                          copy_tone: str = Form("casual"), platforms: str = Form(""), youtube_format: str = Form("vertical")):
        selected = [key for key in platforms.split(",") if key in PLATFORMS]
        if not selected:
            return JSONResponse({"error": "Turn on at least one destination below, then generate drafts."}, status_code=400)
        if copy_tone not in {"casual", "direct", "playful"}:
            return JSONResponse({"error": "Choose a supported voice."}, status_code=400)
        posts = generate_posts({"post_copy": {"enabled": True, "game": copy_game[:60], "creator": copy_creator[:60], "tone": copy_tone}, "platforms": {"youtube": {"format": youtube_format}}})
        return {"drafts": [{"platform": PLATFORMS[key], **posts[key]} for key in selected]}

    @app.post("/connections/youtube/connect")
    def connect_youtube():
        try:
            get_youtube_credentials(cfg.get("youtube") or {}, timeout_seconds=120)
        except Exception:
            return RedirectResponse("/clip?err=" + quote("YouTube connection was not completed. Try again and finish Google sign-in. If connection setup is missing, contact the app administrator.") + "#publish", status_code=303)
        return RedirectResponse("/clip?msg=" + quote("YouTube account connected. Choose your upload settings in the YouTube tile.") + "#publish", status_code=303)

    @app.post("/connections/tiktok/connect")
    def connect_tiktok():
        try:
            tiktok_cfg = dict((cfg.get("platforms") or {}).get("tiktok") or {})
            tiktok_cfg["review"] = dict(cfg.get("review") or {})
            url = begin_authorization(tiktok_cfg)
            webbrowser.open(url, new=2, autoraise=True)
        except Exception as exc:  # noqa: BLE001 — the UI gets a safe next step
            message = str(exc) if isinstance(exc, (NotConfiguredError, TikTokAPIError)) else "TikTok connection could not be started. Check the local setup and try again."
            return RedirectResponse("/clip?err=" + quote(message) + "#publish", status_code=303)
        return RedirectResponse("/clip?msg=" + quote("TikTok sign-in opened in your browser. Finish authorization, then return here.") + "#publish", status_code=303)

    @app.get("/connections/tiktok/callback")
    def tiktok_callback(code: str | None = Query(None), state: str | None = Query(None), error: str | None = Query(None), error_description: str | None = Query(None)):
        if error:
            detail = error_description or error
            return RedirectResponse("/clip?err=" + quote(f"TikTok authorization was not completed: {detail}") + "#publish", status_code=303)
        if not code or not state:
            return RedirectResponse("/clip?err=" + quote("TikTok did not return a complete authorization response. Try Connect TikTok again.") + "#publish", status_code=303)
        try:
            tiktok_cfg = dict((cfg.get("platforms") or {}).get("tiktok") or {})
            tiktok_cfg["review"] = dict(cfg.get("review") or {})
            finish_authorization(tiktok_cfg, code=code, state=state)
        except Exception as exc:  # noqa: BLE001
            message = str(exc) if isinstance(exc, (NotConfiguredError, TikTokAPIError)) else "TikTok authorization could not be saved. Try connecting again."
            return RedirectResponse("/clip?err=" + quote(message) + "#publish", status_code=303)
        return RedirectResponse("/clip?msg=" + quote("TikTok connected. Save Direct post in the TikTok tile to enable live posting.") + "#publish", status_code=303)

    @app.post("/publishing")
    def save_publishing(
        youtube_format: str = Form("vertical"),
        tiktok_format: str = Form("vertical"),
        instagram_format: str = Form("vertical"),
        facebook_format: str = Form("vertical"),
        twitter_format: str = Form("vertical"),
        rumble_format: str = Form("vertical"),
        copy_enabled: str | None = Form(None),
        copy_game: str = Form(""),
        copy_creator: str = Form(""),
        copy_tone: str = Form("casual"),
        publishing_mode: str = Form("review"),
        youtube_enabled: str | None = Form(None),
        youtube_privacy: str = Form("unlisted"),
        youtube_title: str = Form("Highlight {timestamp}"),
        youtube_description: str = Form(""),
        youtube_tags: str = Form(""),
        youtube_category: str = Form("20"),
        youtube_secrets: str | None = Form(None),
        youtube_token: str | None = Form(None),
        tiktok_enabled: str | None = Form(None),
        tiktok_mode: str = Form("manual"),
        tiktok_privacy: str = Form("SELF_ONLY"),
        instagram_enabled: str | None = Form(None),
        instagram_mode: str = Form("manual"),
        facebook_enabled: str | None = Form(None),
        facebook_mode: str = Form("manual"),
        twitter_enabled: str | None = Form(None),
        twitter_mode: str = Form("manual"),
        rumble_enabled: str | None = Form(None),
        rumble_mode: str = Form("manual"),
        tiktok_title: str = Form(""), tiktok_description: str = Form(""), tiktok_tags: str = Form(""),
        instagram_title: str = Form(""), instagram_description: str = Form(""), instagram_tags: str = Form(""),
        facebook_title: str = Form(""), facebook_description: str = Form(""), facebook_tags: str = Form(""),
        twitter_title: str = Form(""), twitter_description: str = Form(""), twitter_tags: str = Form(""),
        rumble_title: str = Form(""), rumble_description: str = Form(""), rumble_tags: str = Form(""),
    ) -> RedirectResponse:
        formats = dict(youtube=youtube_format, tiktok=tiktok_format, instagram=instagram_format,
                       facebook=facebook_format, twitter=twitter_format, rumble=rumble_format)
        if any(value not in FORMATS[key] for key, value in formats.items()):
            return RedirectResponse("/clip?err=Unsupported%20output%20format", status_code=303)
        if publishing_mode not in {"review", "automatic"}:
            return RedirectResponse("/clip?err=Invalid%20publishing%20mode", status_code=303)
        if copy_tone not in {"casual", "direct", "playful"} or len(copy_game) > 60 or len(copy_creator) > 60:
            return RedirectResponse("/clip?err=Invalid%20post%20writing%20settings", status_code=303)
        privacy = youtube_privacy.strip().lower()
        if privacy not in {"private", "unlisted", "public"}:
            return RedirectResponse(
                "/?err=" + quote("Invalid YouTube privacy setting."), status_code=303
            )

        youtube = dict(cfg.get("youtube") or {})
        youtube.update(
            {
                "enabled": youtube_enabled is not None and not dry_run_forced(),
                "privacy": privacy,
                "title_template": youtube_title.strip() or "Highlight {timestamp}",
                "description": youtube_description.strip(),
                "tags": [tag.strip() for tag in youtube_tags.split(",") if tag.strip()],
                "category_id": youtube_category.strip() or "20",
                "client_secrets_file": (youtube_secrets.strip() if youtube_secrets else youtube.get("client_secrets_file")) or "credentials.json",
                "token_file": (youtube_token.strip() if youtube_token else youtube.get("token_file")) or "token.json",
            }
        )
        cfg["youtube"] = youtube

        platforms = dict(cfg.get("platforms") or {})
        platforms["youtube"] = {"enabled": youtube["enabled"], "format": youtube_format}
        incoming = {
            "tiktok": (tiktok_enabled, tiktok_mode, tiktok_title, tiktok_description, tiktok_tags),
            "instagram": (instagram_enabled, instagram_mode, instagram_title, instagram_description, instagram_tags),
            "facebook": (facebook_enabled, facebook_mode, facebook_title, facebook_description, facebook_tags),
            "twitter": (twitter_enabled, twitter_mode, twitter_title, twitter_description, twitter_tags),
            "rumble": (rumble_enabled, rumble_mode, rumble_title, rumble_description, rumble_tags),
        }
        for key, (enabled, raw_mode, title, description, tags) in incoming.items():
            mode = raw_mode.strip().lower()
            allowed_modes = {"manual", "api", "upload"} if key == "tiktok" else {"manual"}
            if mode not in allowed_modes:
                return RedirectResponse("/clip?err=" + quote(f"Invalid {key} delivery mode.") + "#publish", status_code=303)
            current = dict(platforms.get(key) or {})
            current.update({"enabled": enabled is not None, "mode": mode})
            current["format"] = formats[key]
            if key == "tiktok":
                privacy_level = tiktok_privacy.strip().upper()
                if privacy_level not in {"SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"}:
                    return RedirectResponse("/clip?err=" + quote("Choose a valid TikTok privacy setting.") + "#publish", status_code=303)
                current["privacy_level"] = privacy_level
            if any(str(value or "").strip() for value in (title, description, tags)):
                current.update({
                    "title_template": title.strip(),
                    "description": description.strip(),
                    "tags": [tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip().lstrip("#")],
                })
            else:
                for field in ("title_template", "description", "tags"):
                    current.pop(field, None)
            platforms[key] = current
        cfg["platforms"] = platforms
        review = dict(cfg.get("review") or {})
        review["require_approval"] = publishing_mode != "automatic"
        cfg["review"] = review
        cfg["post_copy"] = {"enabled": copy_enabled is not None, "game": copy_game.strip(), "creator": copy_creator.strip(), "tone": copy_tone}
        save_config(cfg)
        return RedirectResponse(
            "/clip?msg=" + quote("Publishing destinations saved.") + "#publish",
            status_code=303,
        )
