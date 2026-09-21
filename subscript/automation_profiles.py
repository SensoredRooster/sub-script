"""Separate, one-profile-at-a-time automation setup and management."""

from __future__ import annotations

from copy import deepcopy
from html import escape
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from subscript import capture_setup
from subscript.config import save_config
from subscript.output_formats import FORMATS, selected_format


def _profiles(cfg: dict) -> list[dict]:
    raw = cfg.get("automation_profiles") or []
    return [dict(item) for item in raw if isinstance(item, dict) and item.get("id")]


def _profile(cfg: dict, profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    return next((item for item in _profiles(cfg) if item.get("id") == profile_id), None)


def _profile_cfg(cfg: dict, profile: dict | None) -> dict:
    result = deepcopy(cfg)
    if profile and isinstance(profile.get("platforms"), dict):
        result["platforms"] = deepcopy(profile["platforms"])
    elif profile is None:
        # A new profile starts clean; existing global publishing choices belong
        # to the studio, not automatically to a new folder-owned profile.
        result["platforms"] = {}
    return result


def _text(form, name: str, default: str = "") -> str:
    value = form.get(name, default)
    return str(value if value is not None else default).strip()


def _selected_platforms(form) -> set[str]:
    allowed = {item[0] for item in capture_setup._AUTOMATION_PROFILES}
    return {str(value) for value in form.getlist("flow_platform") if str(value) in allowed}


def _render_page(cfg: dict, snip, holder: dict, *, profile: dict | None = None, message: str = "", error: str = "") -> str:
    editor_cfg = _profile_cfg(cfg, profile)
    title = "Edit automated profile" if profile else "Create an automated profile"
    subtitle = (
        "Update this profile without changing your other folders."
        if profile
        else "Build one trigger, one folder, and one posting plan at a time."
    )
    template = snip("automation_profile.html")
    delete_control = ""
    if profile:
        delete_control = (
            '<form method="post" action="/automation/delete" class="profile-delete-form" '
            'onsubmit="return confirm(\'Delete this automated profile? Its saved settings will be removed.\');">'
            f'<input type="hidden" name="profile_id" value="{escape(str(profile.get("id") or ""), quote=True)}">'
            '<button type="submit" class="danger-link">Delete this profile</button></form>'
        )
    html = (template
            .replace("{{SIDEBAR}}", sidebar_html(cfg, holder, escape))
            .replace("{{PROFILE_ID}}", escape(str((profile or {}).get("id") or ""), quote=True))
            .replace("{{PROFILE_NAME}}", escape(str((profile or {}).get("name") or ""), quote=True))
            .replace("{{PROFILE_TITLE}}", title)
            .replace("{{PROFILE_SUBTITLE}}", subtitle)
            .replace("{{FOLDER}}", escape(str((profile or {}).get("folder") or ""), quote=True))
            .replace("{{HOTKEY}}", escape(str((profile or {}).get("hotkey") or cfg.get("hotkey") or "ctrl+shift+c"), quote=True))
            .replace("{{SECONDS}}", str(int((profile or {}).get("buffer_seconds") or cfg.get("buffer_seconds") or 30)))
            .replace("{{FLOW_REVIEW_SELECTED}}", "selected" if (profile or {}).get("review_mode", "review") == "review" else "")
            .replace("{{FLOW_AUTO_SELECTED}}", "selected" if (profile or {}).get("review_mode") == "automatic" else "")
            .replace("{{AUTOMATION_PROFILES}}", capture_setup._profile_setup_html(editor_cfg))
            .replace("{{DELETE_CONTROL}}", delete_control)
            .replace("{{MESSAGE}}", f'<p class="banner ok-banner">{escape(message)}</p>' if message else "")
            .replace("{{ERROR}}", f'<p class="banner bad-banner">{escape(error)}</p>' if error else ""))
    return html


def sidebar_html(cfg: dict, holder: dict, esc) -> str:
    profiles = _profiles(cfg)
    rows = []
    watchers = holder.get("profiles") or {}
    for profile in profiles:
        watcher = watchers.get(profile["id"])
        state = "Running" if watcher and watcher.armed else ("Saved" if profile.get("enabled") else "Paused")
        rows.append(
            f'<a class="profile-nav-item" href="/automation/{esc(profile["id"])}/edit">'
            f'<strong>{esc(profile.get("name") or "Unnamed profile")}</strong>'
            f'<small>{esc(state)} · {esc(Path(str(profile.get("folder") or "")).name or "folder")}</small></a>'
        )
    profile_list = "".join(rows) or '<p class="sidebar-empty">No automated profiles yet.</p>'
    return (
        '<aside class="app-sidebar" aria-label="SubScript menu">'
        '<p class="sidebar-kicker">Workspace</p>'
        '<nav class="sidebar-links">'
        '<a href="/#source">Create a clip</a><a href="/#style">Branding</a>'
        '<a href="/#review">Review queue</a><a href="/#publish">Publishing</a>'
        '</nav>'
        '<div class="sidebar-heading"><span>Automated profiles</span>'
        '<a href="/automation/new" aria-label="Create automated profile">+</a></div>'
        f'<div class="profile-nav-list">{profile_list}</div>'
        '<a class="sidebar-create" href="/automation/new">+ Create automated profile</a>'
        '</aside>'
    )


def _validate_folder(folder: str) -> Path:
    path = Path(folder.strip().strip('"')).expanduser()
    if not folder.strip() or not path.is_dir():
        raise ValueError("Replay folder not found. Choose the folder where this profile's VODs are saved.")
    return path.resolve()


def _validate_hotkey(hotkey: str) -> str:
    spec = hotkey.strip().lower()
    if not capture_setup.re.fullmatch(r"(?:(?:ctrl|alt|shift)\+)+[a-z0-9]", spec):
        raise ValueError("Use a shortcut such as ctrl+shift+c: Ctrl, Alt or Shift plus one letter or number.")
    return spec


def _build_profile(cfg: dict, form, existing: dict | None, action: str) -> dict:
    folder = _validate_folder(_text(form, "folder"))
    hotkey = _validate_hotkey(_text(form, "hotkey", "ctrl+shift+c"))
    try:
        seconds = int(_text(form, "seconds", "30"))
    except ValueError as exc:
        raise ValueError("Clip length must be a whole number between 5 and 300 seconds.") from exc
    if not 5 <= seconds <= 300:
        raise ValueError("Choose a clip length between 5 and 300 seconds.")
    review_mode = _text(form, "review_mode", "review")
    if review_mode not in {"review", "automatic"}:
        raise ValueError("Choose Review first or Publish automatically.")
    selected = _selected_platforms(form)
    if review_mode == "automatic" and not selected:
        raise ValueError("Choose at least one posting profile before starting automatic publishing.")
    if not capture_setup.find_ffmpeg():
        raise ValueError("FFmpeg is missing. Install the video processor or place ffmpeg.exe beside the app, then retry.")

    current_platforms = deepcopy((existing or {}).get("platforms") or cfg.get("platforms") or {})
    for key, _name, _detail, mode_options in capture_setup._AUTOMATION_PROFILES:
        current = dict(current_platforms.get(key) or {})
        current["enabled"] = key in selected
        mode = _text(form, f"flow_{key}_mode", "manual").lower()
        fmt = _text(form, f"flow_{key}_format", "vertical").lower()
        valid_modes = {value for value, _label in zip(mode_options[::2], mode_options[1::2])}
        if mode not in valid_modes:
            raise ValueError(f"Invalid {key} delivery mode.")
        if fmt not in FORMATS[key]:
            raise ValueError(f"Invalid {key} output format.")
        current["mode"], current["format"] = mode, fmt
        title = _text(form, f"flow_{key}_title")
        description = _text(form, f"flow_{key}_description")
        tags = _text(form, f"flow_{key}_tags")
        if any((title, description, tags)):
            current.update(
                title_template=title,
                description=description,
                tags=[tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip().lstrip("#")],
            )
        else:
            for field in ("title_template", "description", "tags"):
                current.pop(field, None)
        current_platforms[key] = current

    name = _text(form, "profile_name") or folder.name or "Automated profile"
    return {
        "id": str((existing or {}).get("id") or uuid4().hex[:12]),
        "name": name[:80],
        "folder": str(folder),
        "hotkey": hotkey,
        "buffer_seconds": seconds,
        "review_mode": review_mode,
        "platforms": current_platforms,
        "enabled": action == "save_and_start" or (bool((existing or {}).get("enabled")) and action != "pause"),
    }


def _save_profile(cfg: dict, profile: dict) -> None:
    profiles = _profiles(cfg)
    for item in profiles:
        if item["id"] != profile["id"] and Path(str(item.get("folder") or "")).resolve() == Path(profile["folder"]).resolve():
            raise ValueError("That VOD folder already belongs to another automated profile. Choose a different folder.")
    replaced = False
    for index, item in enumerate(profiles):
        if item["id"] == profile["id"]:
            profiles[index] = profile
            replaced = True
            break
    if not replaced:
        profiles.append(profile)
    cfg["automation_profiles"] = profiles
    save_config(cfg)


def register_automation_routes(app, cfg: dict, holder: dict, snip) -> None:
    @app.get("/automation/new", response_class=HTMLResponse)
    def new_profile() -> str:
        return _render_page(cfg, snip, holder)

    @app.get("/automation/{profile_id}/edit", response_class=HTMLResponse)
    def edit_profile(profile_id: str, msg: str | None = None, err: str | None = None) -> str:
        profile = _profile(cfg, profile_id)
        if not profile:
            return _render_page(cfg, snip, holder, error="That automated profile no longer exists.")
        return _render_page(cfg, snip, holder, profile=profile, message=msg or "", error=err or "")

    @app.post("/automation/save")
    async def save_profile(request: Request) -> RedirectResponse:
        form = await request.form()
        profile_id = _text(form, "profile_id")
        existing = _profile(cfg, profile_id)
        action = _text(form, "action", "save")
        try:
            if action not in {"test", "save", "save_and_start"}:
                raise ValueError("Choose test, save, or save and start.")
            profile = _build_profile(cfg, form, existing, action)
            if action == "test":
                source = capture_setup.newest_video_in(Path(profile["folder"]))
                if source is None:
                    raise ValueError("No replay found in this profile folder. Save a VOD there, then test again.")
                test_cfg = deepcopy(cfg)
                test_cfg.update(watch_folder=profile["folder"], live_source="", hotkey=profile["hotkey"], buffer_seconds=profile["buffer_seconds"])
                test_cfg["platforms"] = deepcopy(profile["platforms"])
                test_cfg.setdefault("review", {})["require_approval"] = True
                capture_setup.run_pipeline(source, test_cfg, dry_run=True, duration=profile["buffer_seconds"])
                profile["enabled"] = False
                _save_profile(cfg, profile)
                return RedirectResponse(f"/automation/{profile['id']}/edit?msg=" + quote("Safe preview created. Nothing was published."), status_code=303)
            _save_profile(cfg, profile)
            if action == "save_and_start":
                from subscript.live_ui import ensure_profile_watcher, stop_profile_watcher
                # Rebuild the callback so edits to folder, delivery, or copy
                # settings take effect immediately for an already-running profile.
                stop_profile_watcher(holder, profile["id"])
                watcher = ensure_profile_watcher(holder, cfg, profile)
                watcher.start()
                message = f"Profile '{profile['name']}' is saved and running."
            else:
                from subscript.live_ui import stop_profile_watcher
                if profile.get("enabled"):
                    from subscript.live_ui import ensure_profile_watcher
                    stop_profile_watcher(holder, profile["id"])
                    ensure_profile_watcher(holder, cfg, profile).start()
                    message = f"Profile '{profile['name']}' is saved and still running."
                else:
                    stop_profile_watcher(holder, profile["id"])
                    message = f"Profile '{profile['name']}' is saved."
            return RedirectResponse("/?msg=" + quote(message) + "#source", status_code=303)
        except Exception as exc:  # noqa: BLE001 — keep the user in the current stepper
            target = f"/automation/{profile_id}/edit" if existing else "/automation/new"
            return RedirectResponse(target + "?err=" + quote(str(exc)), status_code=303)

    @app.post("/automation/delete")
    async def delete_profile(request: Request) -> RedirectResponse:
        form = await request.form()
        profile_id = _text(form, "profile_id")
        profile = _profile(cfg, profile_id)
        if profile:
            from subscript.live_ui import stop_profile_watcher
            stop_profile_watcher(holder, profile_id)
            cfg["automation_profiles"] = [item for item in _profiles(cfg) if item["id"] != profile_id]
            save_config(cfg)
            return RedirectResponse("/?msg=" + quote(f"Profile '{profile.get('name') or 'Unnamed profile'}' was deleted.") + "#source", status_code=303)
        return RedirectResponse("/?err=" + quote("That automated profile was already removed.") + "#source", status_code=303)
