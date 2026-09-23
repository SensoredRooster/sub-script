"""Separate, one-profile-at-a-time automation setup and management."""

from __future__ import annotations

from copy import deepcopy
from html import escape
import mimetypes
import re
from pathlib import Path
import os
import subprocess
from urllib.parse import quote
from uuid import uuid4

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from subscript import capture_setup
from subscript.auth import is_authenticated, login_redirect
from subscript.config import save_config
from subscript.output_formats import FORMATS, selected_format
from subscript.layout import layout_from_form, normalize_layout


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
    editing = bool(profile and profile.get("id"))
    title = "Edit automated profile" if editing else "Create an automated profile"
    subtitle = (
        "Update this workflow without changing your other folders."
        if editing
        else "Choose one folder, decide how new videos should be processed, and turn the workflow on."
    )
    template = snip("automation_profile.html")
    delete_control = ""
    if editing:
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
            .replace("{{SOURCE_SMART_SELECTED}}", "selected" if ((profile or {}).get("source_mode") == "smart_highlight" or (profile is None and not (profile or {}).get("source_mode"))) else "")
            .replace("{{SOURCE_WHOLE_SELECTED}}", "selected" if (profile or {}).get("source_mode") == "whole_file" else "")
            .replace("{{SOURCE_LAST_SELECTED}}", "selected" if ((profile is not None and not (profile or {}).get("source_mode")) or (profile or {}).get("source_mode") == "last_seconds") else "")
            .replace("{{SMART_PRE_ROLL}}", str(float((profile or {}).get("smart_pre_roll", 3.0))))
            .replace("{{SMART_POST_ROLL}}", str(float((profile or {}).get("smart_post_roll", 2.0))))
            .replace("{{SECONDS}}", str(int((profile or {}).get("buffer_seconds") or cfg.get("buffer_seconds") or 30)))
            .replace("{{FLOW_REVIEW_SELECTED}}", "selected" if (profile or {}).get("review_mode", "review") == "review" else "")
            .replace("{{FLOW_AUTO_SELECTED}}", "selected" if (profile or {}).get("review_mode") == "automatic" else "")
            .replace("{{AUTOMATION_PROFILES}}", capture_setup._profile_setup_html(editor_cfg))
            .replace("{{VERTICAL_COMPOSER}}", _composer_html(snip, (profile or {}).get("vertical_layout")))
            .replace("{{DELETE_CONTROL}}", delete_control)
            .replace("{{MESSAGE}}", f'<p class="banner ok-banner">{escape(message)}</p>' if message else "")
            .replace("{{ERROR}}", f'<p class="banner bad-banner">{escape(error)}</p>' if error else ""))
    return html


def _composer_html(snip, layout: dict | None) -> str:
    """Fill the shared composer with a saved profile template."""
    html = snip("vertical_composer.html")
    current = normalize_layout(layout)
    mode = current["mode"]
    preset = current["preset"] if mode == "composer" else "gameplay_facecam"
    html = html.replace('<option value="center_crop">', f'<option value="center_crop" {"selected" if mode != "composer" else ""}>')
    html = html.replace('<option value="composer">', f'<option value="composer" {"selected" if mode == "composer" else ""}>')
    for option in ("gameplay_facecam", "facecam_top", "gameplay_top", "gameplay_only", "facecam_overlay", "blurred_background"):
        html = html.replace(f'<option value="{option}">', f'<option value="{option}" {"selected" if option == preset else ""}>')
    if mode == "composer":
        regions, boxes, style = current["regions"], current["boxes"], current["style"]
        for prefix, region in (("gameplay", regions["gameplay"]), ("facecam", regions["facecam"]), ("gameplay_box", boxes["gameplay"]), ("facecam_box", boxes["facecam"])):
            for key, value in region.items():
                html = re.sub(rf'(name="{prefix}_{key}"[^>]*value=")[^"]*(")', rf'\g<1>{value}\2', html)
        html = re.sub(r'(name="vertical_gap"[^>]*value=")[^"]*(")', rf'\g<1>{style["gap"]}\2', html)
        html = re.sub(r'(name="vertical_border"[^>]*value=")[^"]*(")', rf'\g<1>{style["border"]}\2', html)
        html = html.replace(f'<option value="{style["background"]}">', f'<option value="{style["background"]}" selected>')
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
        '<a href="/clip#source">Create a clip</a><a href="/clip#style">Branding</a>'
        '<a href="/clip#review">Review queue</a><a href="/clip#publish">Publishing</a>'
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
    # Keep the legacy hotkey value for backward compatibility, but folder-owned
    # Autopilot profiles are triggered automatically by new completed files.
    hotkey = _text(form, "hotkey", str((existing or {}).get("hotkey") or cfg.get("hotkey") or "ctrl+shift+c")) or "ctrl+shift+c"
    try:
        seconds = int(_text(form, "seconds", "30"))
    except ValueError as exc:
        raise ValueError("Clip length must be a whole number between 5 and 300 seconds.") from exc
    if not 5 <= seconds <= 300:
        raise ValueError("Choose a clip length between 5 and 300 seconds.")
    source_default = str((existing or {}).get("source_mode") or ("last_seconds" if existing else "smart_highlight"))
    source_mode = _text(form, "source_mode", source_default)
    if source_mode not in {"smart_highlight", "whole_file", "last_seconds"}:
        raise ValueError("Choose Smart Highlight, whole incoming video, or last seconds.")
    try:
        smart_pre_roll = float(_text(form, "smart_pre_roll", str((existing or {}).get("smart_pre_roll", 3.0))))
        smart_post_roll = float(_text(form, "smart_post_roll", str((existing or {}).get("smart_post_roll", 2.0))))
    except ValueError as exc:
        raise ValueError("Smart Highlight context values must be numbers.") from exc
    if not 0 <= smart_pre_roll <= 30 or not 0 <= smart_post_roll <= 30:
        raise ValueError("Smart Highlight context must be between 0 and 30 seconds.")
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
        "source_mode": source_mode,
        "smart_pre_roll": smart_pre_roll,
        "smart_post_roll": smart_post_roll,
        "review_mode": review_mode,
        "platforms": current_platforms,
        "vertical_layout": layout_from_form(form),
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


def _management_cards(cfg: dict, holder: dict, esc) -> str:
    profiles = _profiles(cfg)
    watchers = holder.get("profiles") or {}
    labels = {item[0]: item[1] for item in capture_setup._AUTOMATION_PROFILES}
    cards = []
    for profile in profiles:
        profile_id = str(profile["id"])
        watcher = watchers.get(profile_id)
        running = bool(watcher and watcher.armed)
        enabled = bool(profile.get("enabled"))
        state = "Running" if running else ("Ready to start" if enabled else "Paused")
        state_class = "running" if running else ("ready" if enabled else "paused")
        destinations = [
            labels.get(key, key.title())
            for key, settings in (profile.get("platforms") or {}).items()
            if isinstance(settings, dict) and settings.get("enabled")
        ]
        destination_text = ", ".join(destinations) or "No posting destinations yet"
        action = "stop" if running else "start"
        action_label = "Stop watching" if running else "Start watching"
        cards.append(
            '<article class="managed-profile-card">'
            '<header><div><p class="eyebrow">Automated profile</p>'
            f'<h3>{esc(str(profile.get("name") or "Unnamed profile"))}</h3></div>'
            f'<span class="profile-state {state_class}">{esc(state)}</span></header>'
            '<div class="managed-profile-meta">'
            f'<p><strong>Folder</strong><code>{esc(str(profile.get("folder") or "Not set"))}</code></p>'
            f'<p><strong>Clip rule</strong><span>{esc("Smart Highlight" if profile.get("source_mode") == "smart_highlight" else ("Use whole file" if profile.get("source_mode") == "whole_file" else "Keep last " + str(profile.get("buffer_seconds") or 30) + " seconds"))}</span></p>'
            f'<p><strong>Destinations</strong><span>{esc(destination_text)}</span></p>'
            '</div><div class="profile-card-actions">'
            f'<a class="quiet-button" href="/automation/{esc(profile_id)}/edit">Edit workflow</a>'
            f'<a class="quiet-button" href="/automation/{esc(profile_id)}/clone">Duplicate</a>'
            f'<a class="quiet-button" href="/automation/{esc(profile_id)}/open-folder">Open folder</a>'
            f'<form method="post" action="/automation/{esc(profile_id)}/{action}">'
            f'<button class="secondary" type="submit">{esc(action_label)}</button></form>'
            '</div></article>'
        )
    return "".join(cards) or (
        '<div class="management-empty"><h3>No automated workflows yet.</h3>'
        '<p>Build your first workflow and SubScript will watch its folder automatically for new completed videos.</p>'
        '<a class="primary" href="/automation/new">Build my first workflow</a></div>'
    )


def register_automation_routes(app, cfg: dict, holder: dict, snip) -> None:
    @app.get("/automation", response_class=HTMLResponse)
    def automation_management(request: Request, msg: str | None = None, err: str | None = None):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        template = snip("automation_management.html")
        message = f'<p class="banner ok-banner">{escape(msg)}</p>' if msg else ""
        error = f'<p class="banner bad-banner">{escape(err)}</p>' if err else ""
        return (template
                .replace("{{MESSAGE}}", message)
                .replace("{{ERROR}}", error)
                .replace("{{PROFILE_COUNT}}", str(len(_profiles(cfg))))
                .replace("{{PROFILE_CARDS}}", _management_cards(cfg, holder, escape)))

    @app.get("/automation/new", response_class=HTMLResponse)
    def new_profile(request: Request):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        return _render_page(cfg, snip, holder)

    @app.post("/automation/browse-folder")
    def browse_folder(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"error": "Sign in required."}, status_code=401)
        chosen = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askdirectory(title="Choose the folder SubScript should watch")
            root.destroy()
        except Exception:
            if os.name == "nt":
                try:
                    script = (
                        "$s=New-Object -ComObject Shell.Application;"
                        "$f=$s.BrowseForFolder(0,'Choose the folder SubScript should watch',0,0);"
                        "if($f){$f.Self.Path}"
                    )
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", script],
                        capture_output=True, text=True, timeout=120, check=False,
                    )
                    chosen = result.stdout.strip()
                except Exception:
                    chosen = ""
        if not chosen:
            return JSONResponse({"cancelled": True, "folder": ""})
        path = Path(chosen).expanduser()
        if not path.is_dir():
            return JSONResponse({"error": "That folder is not available."}, status_code=400)
        latest = capture_setup.newest_video_in(path)
        count = sum(1 for p in path.iterdir() if p.is_file() and p.suffix.lower() in {".mp4",".mov",".mkv",".webm",".avi",".m4v",".flv",".ts"})
        return JSONResponse({"folder": str(path.resolve()), "video_count": count, "latest": latest.name if latest else ""})

    @app.get("/automation/folder-status")
    def folder_status(request: Request, folder: str = ""):
        if not is_authenticated(request, cfg):
            return JSONResponse({"error": "Sign in required."}, status_code=401)
        path = Path(folder.strip().strip('"')).expanduser()
        if not folder.strip() or not path.is_dir():
            return JSONResponse({"ready": False, "message": "Choose an existing folder."})
        latest = capture_setup.newest_video_in(path)
        count = sum(1 for p in path.iterdir() if p.is_file() and p.suffix.lower() in {".mp4",".mov",".mkv",".webm",".avi",".m4v",".flv",".ts"})
        return JSONResponse({
            "ready": True,
            "folder": str(path.resolve()),
            "video_count": count,
            "latest": latest.name if latest else "",
            "message": ("Folder ready · newest video: " + latest.name) if latest else "Folder ready · no videos here yet",
        })

    @app.post("/automation/open-folder")
    async def open_folder(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"error": "Sign in required."}, status_code=401)
        form = await request.form()
        folder = _text(form, "folder")
        path = Path(folder.strip().strip('"')).expanduser()
        if not path.is_dir():
            return JSONResponse({"error": "Folder not found."}, status_code=404)
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif os.name == "posix":
                subprocess.Popen(["xdg-open", str(path)])
            return JSONResponse({"ok": True})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/automation/source-preview")
    def source_preview(request: Request, folder: str = ""):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        source = capture_setup.newest_video_in(Path(folder.strip().strip('"')).expanduser()) if folder.strip() else None
        if not source:
            return HTMLResponse("No representative VOD found.", status_code=404)
        from fastapi.responses import FileResponse
        mime, _ = mimetypes.guess_type(str(source))
        return FileResponse(source, media_type=mime or "video/mp4")

    @app.get("/automation/{profile_id}/clone", response_class=HTMLResponse)
    def clone_profile(request: Request, profile_id: str):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        source = _profile(cfg, profile_id)
        if not source:
            return _render_page(cfg, snip, holder, error="That workflow no longer exists.")
        clone = deepcopy(source)
        clone.pop("id", None)
        clone["name"] = (str(source.get("name") or "Workflow") + " copy")[:80]
        clone["folder"] = ""
        clone["enabled"] = False
        return _render_page(
            cfg, snip, holder, profile=clone,
            message="Duplicated settings. Choose a different watch folder, then save this as a new workflow.",
        )

    @app.get("/automation/{profile_id}/open-folder")
    def open_profile_folder(request: Request, profile_id: str):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        profile = _profile(cfg, profile_id)
        if not profile:
            return RedirectResponse("/automation?err=" + quote("That workflow no longer exists."), status_code=303)
        path = Path(str(profile.get("folder") or "")).expanduser()
        if not path.is_dir():
            return RedirectResponse("/automation?err=" + quote("That workflow folder is unavailable."), status_code=303)
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif os.name == "posix":
                subprocess.Popen(["xdg-open", str(path)])
            return RedirectResponse("/automation?msg=" + quote("Opened workflow folder."), status_code=303)
        except Exception as exc:
            return RedirectResponse("/automation?err=" + quote(f"Could not open folder: {exc}"), status_code=303)

    @app.get("/automation/{profile_id}/edit", response_class=HTMLResponse)
    def edit_profile(request: Request, profile_id: str, msg: str | None = None, err: str | None = None):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        profile = _profile(cfg, profile_id)
        if not profile:
            return _render_page(cfg, snip, holder, error="That automated profile no longer exists.")
        return _render_page(cfg, snip, holder, profile=profile, message=msg or "", error=err or "")

    @app.post("/automation/{profile_id}/start")
    def start_profile(request: Request, profile_id: str) -> RedirectResponse:
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        profile = _profile(cfg, profile_id)
        if not profile:
            return RedirectResponse("/automation?err=" + quote("That automated profile no longer exists."), status_code=303)
        from subscript.live_ui import ensure_profile_watcher, stop_profile_watcher
        stop_profile_watcher(holder, profile_id)
        profile["enabled"] = True
        _save_profile(cfg, profile)
        ensure_profile_watcher(holder, cfg, profile).start()
        return RedirectResponse("/automation?msg=" + quote(f"'{profile.get('name') or 'Profile'}' is watching for new clips."), status_code=303)

    @app.post("/automation/{profile_id}/stop")
    def stop_profile(request: Request, profile_id: str) -> RedirectResponse:
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        profile = _profile(cfg, profile_id)
        if not profile:
            return RedirectResponse("/automation?err=" + quote("That automated profile no longer exists."), status_code=303)
        from subscript.live_ui import stop_profile_watcher
        stop_profile_watcher(holder, profile_id)
        profile["enabled"] = False
        _save_profile(cfg, profile)
        return RedirectResponse("/automation?msg=" + quote(f"'{profile.get('name') or 'Profile'}' is paused."), status_code=303)

    @app.post("/automation/save")
    async def save_profile(request: Request) -> RedirectResponse:
        if not is_authenticated(request, cfg):
            return login_redirect(request)
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
                    raise ValueError("No video found in this watched folder. Add a finished video there, then run the safe test again.")
                test_cfg = deepcopy(cfg)
                test_cfg.update(watch_folder=profile["folder"], live_source="", hotkey=profile["hotkey"], buffer_seconds=profile["buffer_seconds"])
                test_cfg["platforms"] = deepcopy(profile["platforms"])
                test_cfg["vertical_layout"] = deepcopy(profile.get("vertical_layout") or {})
                test_cfg.setdefault("review", {})["require_approval"] = True
                if profile.get("source_mode", "smart_highlight") == "smart_highlight":
                    from subscript.live_ui import smart_highlight_window
                    start, test_duration, _note = smart_highlight_window(source, test_cfg, profile)
                    capture_setup.run_pipeline(source, test_cfg, dry_run=True, start=start, duration=test_duration)
                else:
                    test_duration = None if profile.get("source_mode") == "whole_file" else profile["buffer_seconds"]
                    capture_setup.run_pipeline(source, test_cfg, dry_run=True, duration=test_duration)
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
            return RedirectResponse("/?msg=" + quote(message), status_code=303)
        except Exception as exc:  # noqa: BLE001 — keep the user in the current stepper
            target = f"/automation/{profile_id}/edit" if existing else "/automation/new"
            return RedirectResponse(target + "?err=" + quote(str(exc)), status_code=303)

    @app.post("/automation/delete")
    async def delete_profile(request: Request) -> RedirectResponse:
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        form = await request.form()
        profile_id = _text(form, "profile_id")
        profile = _profile(cfg, profile_id)
        if profile:
            from subscript.live_ui import stop_profile_watcher
            stop_profile_watcher(holder, profile_id)
            cfg["automation_profiles"] = [item for item in _profiles(cfg) if item["id"] != profile_id]
            save_config(cfg)
            return RedirectResponse("/?msg=" + quote(f"Profile '{profile.get('name') or 'Unnamed profile'}' was deleted."), status_code=303)
        return RedirectResponse("/?err=" + quote("That automated profile was already removed."), status_code=303)
