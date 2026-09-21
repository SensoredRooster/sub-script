"""Guided capture settings; test renders never publish."""
from copy import deepcopy
from html import escape
from pathlib import Path
import re
from urllib.parse import quote

from fastapi import Form
from fastapi.responses import RedirectResponse
from subscript.buffer import newest_video_in
from subscript.config import save_config
from subscript.output_formats import FORMATS, selected_format
from subscript.pipeline import run_pipeline
from subscript.runtime_paths import find_ffmpeg


_AUTOMATION_PROFILES = (
    ("youtube", "YouTube", "Shorts or landscape video", ("manual", "Upload pack")),
    ("tiktok", "TikTok", "Direct post, draft, or upload pack", ("manual", "Local upload pack", "api", "Direct post", "upload", "TikTok draft")),
    ("instagram", "Instagram", "Reels-ready vertical video", ("manual", "Upload pack")),
    ("facebook", "Facebook", "Reels-ready vertical video", ("manual", "Upload pack")),
    ("twitter", "X / Twitter", "Social-ready video", ("manual", "Upload pack")),
    ("rumble", "Rumble", "Upload-ready video", ("manual", "Upload pack")),
)


def _profile_setup_html(cfg):
    platforms = dict(cfg.get("platforms") or {})
    cards = []
    for key, name, detail, mode_options in _AUTOMATION_PROFILES:
        item = dict(platforms.get(key) or {})
        if key == "youtube":
            enabled = bool(item.get("enabled") or (cfg.get("youtube") or {}).get("enabled"))
        else:
            enabled = bool(item.get("enabled"))
        mode = str(item.get("mode") or "manual")
        format_value = selected_format(cfg, key)
        title = escape(str(item.get("title_template") or ""), quote=True)
        description = escape(str(item.get("description") or ""))
        raw_tags = item.get("tags") or []
        tags = escape(raw_tags if isinstance(raw_tags, str) else ", ".join(str(tag) for tag in raw_tags), quote=True)
        mode_markup = "".join(
            f'<option value="{escape(value)}" {"selected" if mode == value else ""}>{escape(label)}</option>'
            for value, label in zip(mode_options[::2], mode_options[1::2])
        )
        format_markup = "".join(
            f'<option value="{escape(value)}" {"selected" if format_value == value else ""}>{escape(label)}</option>'
            for value, label in FORMATS[key].items()
        )
        cards.append(
            f'<article class="automation-profile" data-profile-key="{key}">'
            f'<label class="profile-toggle"><input type="checkbox" name="flow_platform" value="{key}" {"checked" if enabled else ""} data-profile-toggle>'
            f'<span><strong>{escape(name)}</strong><small>{escape(detail)}</small></span></label>'
            f'<div class="profile-fields">'
            f'<label>Delivery<select name="flow_{key}_mode">{mode_markup}</select></label>'
            f'<label>Format<select name="flow_{key}_format">{format_markup}</select></label>'
            f'<label>Title / caption <span class="field-hint">optional</span><input name="flow_{key}_title" type="text" maxlength="95" value="{title}" placeholder="Leave blank for automatic copy"></label>'
            f'<label>Description <span class="field-hint">optional</span><textarea name="flow_{key}_description" rows="2" maxlength="1800">{description}</textarea></label>'
            f'<label>Tags <span class="field-hint">comma separated</span><input name="flow_{key}_tags" type="text" value="{tags}" placeholder="gaming, highlights"></label>'
            f'</div></article>'
        )
    return "".join(cards)


def setup_html(cfg, snip):
    review_mode = "review" if (cfg.get("review") or {}).get("require_approval", True) else "automatic"
    return (snip("capture_setup.html")
            .replace("{{FOLDER}}", escape(str(cfg.get("watch_folder") or ""), quote=True))
            .replace("{{CAPTURE_HOTKEY}}", escape(str(cfg.get("hotkey") or "ctrl+shift+c"), quote=True))
            .replace("{{SECONDS}}", str(int(cfg.get("buffer_seconds") or 30)))
            .replace("{{FLOW_REVIEW_SELECTED}}", "selected" if review_mode == "review" else "")
            .replace("{{FLOW_AUTO_SELECTED}}", "selected" if review_mode == "automatic" else "")
            .replace("{{AUTOMATION_PROFILES}}", _profile_setup_html(cfg)))


def register_capture_setup(app, cfg, holder):
    @app.post("/capture/setup")
    def configure(folder: str = Form(""), hotkey: str = Form("ctrl+shift+c"),
                  seconds: int = Form(30), review_mode: str = Form("review"),
                  action: str = Form("save"), flow_profile_setup: str = Form(""),
                  flow_platform: list[str] = Form(default=[]),
                  flow_tiktok_mode: str = Form("manual"), flow_tiktok_format: str = Form("vertical"),
                  flow_tiktok_title: str = Form(""), flow_tiktok_description: str = Form(""), flow_tiktok_tags: str = Form(""),
                  flow_youtube_mode: str = Form("manual"), flow_youtube_format: str = Form("vertical"),
                  flow_youtube_title: str = Form(""), flow_youtube_description: str = Form(""), flow_youtube_tags: str = Form(""),
                  flow_instagram_mode: str = Form("manual"), flow_instagram_format: str = Form("vertical"),
                  flow_instagram_title: str = Form(""), flow_instagram_description: str = Form(""), flow_instagram_tags: str = Form(""),
                  flow_facebook_mode: str = Form("manual"), flow_facebook_format: str = Form("vertical"),
                  flow_facebook_title: str = Form(""), flow_facebook_description: str = Form(""), flow_facebook_tags: str = Form(""),
                  flow_twitter_mode: str = Form("manual"), flow_twitter_format: str = Form("vertical"),
                  flow_twitter_title: str = Form(""), flow_twitter_description: str = Form(""), flow_twitter_tags: str = Form(""),
                  flow_rumble_mode: str = Form("manual"), flow_rumble_format: str = Form("vertical"),
                  flow_rumble_title: str = Form(""), flow_rumble_description: str = Form(""), flow_rumble_tags: str = Form("")):
        try:
            if action not in {"save", "save_and_start", "test"}:
                raise ValueError("Choose a workflow action: test, save, or save and start.")
            if review_mode not in {"review", "automatic"}:
                raise ValueError("Choose Review first or Publish automatically.")
            path = Path(folder.strip().strip('"')).expanduser()
            if not folder.strip() or not path.is_dir():
                raise ValueError("Replay folder not found. Copy the recording folder from your recorder settings.")
            spec = hotkey.strip().lower()
            if not re.fullmatch(r"(?:(?:ctrl|alt|shift)\+)+[a-z0-9]", spec):
                raise ValueError("Use a shortcut such as ctrl+shift+c: Ctrl, Alt or Shift plus one letter or number.")
            if not 5 <= seconds <= 300:
                raise ValueError("Choose a clip length between 5 and 300 seconds.")
            if not find_ffmpeg():
                raise ValueError("FFmpeg is missing. Install the video processor or place ffmpeg.exe beside the app, then retry.")
            selected_profiles = {key for key in flow_platform if key in {item[0] for item in _AUTOMATION_PROFILES}}
            if flow_profile_setup and review_mode == "automatic" and not selected_profiles:
                raise ValueError("Choose at least one posting profile before starting automatic publishing.")
            if action == "test":
                source = newest_video_in(path)
                if source is None:
                    raise ValueError("No replay found. Start your recorder's replay buffer, save a replay, then retry.")
                test_cfg = deepcopy(cfg)
                test_cfg.setdefault("review", {})["require_approval"] = True
                test_cfg["buffer_seconds"] = seconds
                run_pipeline(source, test_cfg, dry_run=True, duration=seconds)
                message = "Test preview created from " + source.name + ". Nothing was uploaded. Check Review, then save setup and start the watcher."
            else:
                updated = deepcopy(cfg)
                updated.update(watch_folder=str(path.resolve()), live_source="", hotkey=spec, buffer_seconds=seconds, auto_start_watcher=action == "save_and_start")
                updated.setdefault("review", {})["require_approval"] = review_mode == "review"
                if flow_profile_setup and selected_profiles:
                    platforms = dict(updated.get("platforms") or {})
                    for key, _name, _detail, _mode_options in _AUTOMATION_PROFILES:
                        current = dict(platforms.get(key) or {})
                        current["enabled"] = key in selected_profiles
                        mode = locals()[f"flow_{key}_mode"].strip().lower()
                        fmt = locals()[f"flow_{key}_format"].strip().lower()
                        if mode not in {value for value, _label in zip(_mode_options[::2], _mode_options[1::2])}:
                            raise ValueError(f"Invalid {key} delivery mode.")
                        if fmt not in FORMATS[key]:
                            raise ValueError(f"Invalid {key} output format.")
                        current["mode"] = mode
                        current["format"] = fmt
                        title = locals()[f"flow_{key}_title"].strip()
                        description = locals()[f"flow_{key}_description"].strip()
                        tags = locals()[f"flow_{key}_tags"].strip()
                        if any((title, description, tags)):
                            current.update(title_template=title, description=description,
                                          tags=[tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip().lstrip("#")])
                        else:
                            for field in ("title_template", "description", "tags"):
                                current.pop(field, None)
                        platforms[key] = current
                    updated["platforms"] = platforms
                save_config(updated)
                watcher = holder.get("w")
                if watcher:
                    watcher.stop()
                holder["w"] = None
                cfg.update(updated)
                if action == "save_and_start":
                    try:
                        from subscript.live_ui import ensure_watcher
                        watcher = ensure_watcher(holder, cfg)
                        watcher.start()
                        message = "Automated workflow saved and started. Save a replay, wait for it to finish, then press " + spec + "."
                    except Exception as exc:  # noqa: BLE001 — setup remains saved
                        message = "Flow saved, but the watcher could not start: " + str(exc)
                else:
                    message = "Automated workflow saved. Start the watcher when you are ready to play."
            return RedirectResponse("/clip?msg=" + quote(message) + ("#review" if action == "test" else "#capture-setup"), status_code=303)
        except Exception as exc:
            return RedirectResponse("/clip?err=" + quote(str(exc)) + "#capture-setup", status_code=303)
