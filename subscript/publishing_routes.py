"""User-facing publishing settings panel and routes."""

from __future__ import annotations

from collections.abc import Callable
from html import escape
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse

from subscript.config import dry_run_forced, save_config

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
        mode = str(item.get("mode") or "manual").lower()
        cards.append(
            '<article class="platform-card">'
            '<div class="platform-card-head">'
            f'<span class="platform-mark platform-{key}">{escape(name[:1])}</span>'
            f"<div><h3>{escape(name)}</h3><p>{escape(detail)}</p></div>"
            '<label class="switch" aria-label="Enable '
            f'{escape(name)}"><input type="checkbox" name="{key}_enabled" value="1" '
            f"{_checked(item.get('enabled'))}><span></span></label></div>"
            '<label>Delivery method<select name="'
            f'{key}_mode"><option value="manual" '
            f"{_selected(mode, 'manual')}>Manual handoff pack</option>"
            f'<option value="api" {_selected(mode, "api")} disabled>'
            "API connection — coming later</option>"
            "</select></label></article>"
        )

    return (
        snip("publishing.html")
        .replace("{{COPY_ENABLED}}", _checked((cfg.get("post_copy") or {}).get("enabled", True)))
        .replace("{{COPY_GAME}}", escape(str((cfg.get("post_copy") or {}).get("game") or ""), quote=True))
        .replace("{{COPY_CREATOR}}", escape(str((cfg.get("post_copy") or {}).get("creator") or ""), quote=True))
        .replace("{{TONE_CASUAL}}", _selected((cfg.get("post_copy") or {}).get("tone", "casual"), "casual"))
        .replace("{{TONE_DIRECT}}", _selected((cfg.get("post_copy") or {}).get("tone", "casual"), "direct"))
        .replace("{{TONE_PLAYFUL}}", _selected((cfg.get("post_copy") or {}).get("tone", "casual"), "playful"))
        .replace("{{YT_ENABLED}}", _checked(yt_enabled))
        .replace("{{REVIEW_SELECTED}}", _selected("review" if (cfg.get("review") or {}).get("require_approval", True) else "automatic", "review"))
        .replace("{{AUTO_SELECTED}}", _selected("review" if (cfg.get("review") or {}).get("require_approval", True) else "automatic", "automatic"))
        .replace(
            "{{YT_DRY_RUN}}",
            ""
            if not dry_run_forced()
            else (
                '<p class="inline-alert">Live uploads are currently disabled by '
                "SUB_SCRIPT_DRY_RUN.</p>"
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
        .replace(
            "{{YT_SECRETS}}",
            escape(
                str(youtube.get("client_secrets_file") or "credentials.json"),
                quote=True,
            ),
        )
        .replace(
            "{{YT_TOKEN}}",
            escape(str(youtube.get("token_file") or "token.json"), quote=True),
        )
        .replace("{{PLATFORM_CARDS}}", "\n".join(cards))
    )


def register_publishing_routes(app: FastAPI, cfg: dict[str, Any]) -> None:
    @app.post("/publishing")
    def save_publishing(
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
        youtube_secrets: str = Form("credentials.json"),
        youtube_token: str = Form("token.json"),
        tiktok_enabled: str | None = Form(None),
        tiktok_mode: str = Form("manual"),
        instagram_enabled: str | None = Form(None),
        instagram_mode: str = Form("manual"),
        facebook_enabled: str | None = Form(None),
        facebook_mode: str = Form("manual"),
        twitter_enabled: str | None = Form(None),
        twitter_mode: str = Form("manual"),
        rumble_enabled: str | None = Form(None),
        rumble_mode: str = Form("manual"),
    ) -> RedirectResponse:
        if publishing_mode not in {"review", "automatic"}:
            return RedirectResponse("/?err=Invalid%20publishing%20mode", status_code=303)
        if copy_tone not in {"casual", "direct", "playful"} or len(copy_game) > 60 or len(copy_creator) > 60:
            return RedirectResponse("/?err=Invalid%20post%20writing%20settings", status_code=303)
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
                "client_secrets_file": youtube_secrets.strip() or "credentials.json",
                "token_file": youtube_token.strip() or "token.json",
            }
        )
        cfg["youtube"] = youtube

        platforms = dict(cfg.get("platforms") or {})
        platforms["youtube"] = {"enabled": youtube["enabled"]}
        incoming = {
            "tiktok": (tiktok_enabled, tiktok_mode),
            "instagram": (instagram_enabled, instagram_mode),
            "facebook": (facebook_enabled, facebook_mode),
            "twitter": (twitter_enabled, twitter_mode),
            "rumble": (rumble_enabled, rumble_mode),
        }
        for key, (enabled, raw_mode) in incoming.items():
            mode = raw_mode.strip().lower()
            if mode not in {"manual", "api"}:
                mode = "manual"
            current = dict(platforms.get(key) or {})
            current.update({"enabled": enabled is not None, "mode": mode})
            platforms[key] = current
        cfg["platforms"] = platforms
        review = dict(cfg.get("review") or {})
        review["require_approval"] = publishing_mode != "automatic"
        cfg["review"] = review
        cfg["post_copy"] = {"enabled": copy_enabled is not None, "game": copy_game.strip(), "creator": copy_creator.strip(), "tone": copy_tone}
        save_config(cfg)
        return RedirectResponse(
            "/?msg=" + quote("Publishing destinations saved.") + "#publish",
            status_code=303,
        )
