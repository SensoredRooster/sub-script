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
from subscript.pipeline import run_pipeline
from subscript.runtime_paths import find_ffmpeg


def setup_html(cfg, snip):
    review_mode = "review" if (cfg.get("review") or {}).get("require_approval", True) else "automatic"
    return (snip("capture_setup.html")
            .replace("{{FOLDER}}", escape(str(cfg.get("watch_folder") or ""), quote=True))
            .replace("{{CAPTURE_HOTKEY}}", escape(str(cfg.get("hotkey") or "ctrl+shift+c"), quote=True))
            .replace("{{SECONDS}}", str(int(cfg.get("buffer_seconds") or 30)))
            .replace("{{FLOW_REVIEW_SELECTED}}", "selected" if review_mode == "review" else "")
            .replace("{{FLOW_AUTO_SELECTED}}", "selected" if review_mode == "automatic" else ""))


def register_capture_setup(app, cfg, holder):
    @app.post("/capture/setup")
    def configure(folder: str = Form(""), hotkey: str = Form("ctrl+shift+c"),
                  seconds: int = Form(30), review_mode: str = Form("review"),
                  action: str = Form("save")):
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
            return RedirectResponse("/?msg=" + quote(message) + ("#review" if action == "test" else "#capture-setup"), status_code=303)
        except Exception as exc:
            return RedirectResponse("/?err=" + quote(str(exc)) + "#capture-setup", status_code=303)
