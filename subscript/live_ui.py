"""Live hotkey helpers for the review app UI."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from subscript.buffer import newest_video_in, resolve_live_source
from subscript.hotkey import HotkeyWatcher
from subscript.folder_watcher import FolderWatcher
from subscript.pipeline import run_pipeline
from subscript.highlights import suggest_highlights_or_fallback


def source_hint(cfg: dict[str, Any]) -> str:
    live_source = (cfg.get("live_source") or "").strip()
    watch_folder = (cfg.get("watch_folder") or "").strip()
    if live_source:
        return f"Source: {live_source}"
    if watch_folder:
        newest = newest_video_in(Path(watch_folder))
        if newest:
            return f"Watch folder: {watch_folder} (newest: {newest.name})"
        return f"Watch folder: {watch_folder} (no videos yet)"
    return (
        "Set live_source or watch_folder in config.yaml "
        "(OBS replay buffer path), then Start watcher."
    )


def live_card_html(
    cfg: dict[str, Any],
    watcher: HotkeyWatcher | None,
    *,
    snip,
    esc,
) -> str:
    hotkey = cfg.get("hotkey") or "ctrl+shift+c"
    seconds = int(cfg.get("buffer_seconds") or 30)
    armed = bool(watcher and watcher.armed)
    tpl = snip("live_hotkey.html")
    if watcher and watcher.last_error:
        msg = f"Last error: {watcher.last_error}"
    elif watcher and watcher.last_ok:
        msg = watcher.last_ok
    else:
        msg = source_hint(cfg)
    return (
        tpl.replace("{{BUFFER_SECONDS}}", str(seconds))
        .replace("{{HOTKEY}}", esc(hotkey))
        .replace("{{SOURCE_HINT}}", esc(source_hint(cfg)))
        .replace("{{DOT_CLASS}}", "on" if armed else "off")
        .replace("{{ARMED_LABEL}}", "Armed" if armed else "Not armed")
        .replace("{{LIVE_MSG}}", esc(msg))
        .replace("{{START_DISABLED}}", "disabled" if armed else "")
        .replace("{{STOP_DISABLED}}", "" if armed else "disabled")
    )


def make_fire_live(cfg: dict[str, Any]):
    def _fire_live() -> None:
        seconds = int(cfg.get("buffer_seconds") or 30)
        source = resolve_live_source(cfg)
        live_cfg = dict(cfg)
        run_pipeline(
            source,
            live_cfg,
            dry_run=bool((cfg.get("review") or {}).get("require_approval", True)),
            start=None,
            duration=float(seconds),
        )

    return _fire_live


def ensure_watcher(
    holder: dict[str, HotkeyWatcher | None],
    cfg: dict[str, Any],
) -> HotkeyWatcher:
    w = holder["w"]
    if w is None:
        w = HotkeyWatcher(
            cfg.get("hotkey") or "ctrl+shift+c",
            make_fire_live(cfg),
            notify=bool(cfg.get("notify", True)),
        )
        holder["w"] = w
    return w


def profile_runtime_cfg(cfg: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Build the pipeline config for one folder-owned automation profile."""
    runtime_cfg = deepcopy(cfg)
    runtime_cfg.update(
        watch_folder=str(profile.get("folder") or ""),
        live_source="",
        hotkey=profile.get("hotkey") or "ctrl+shift+c",
        buffer_seconds=int(profile.get("buffer_seconds") or 30),
    )
    runtime_cfg["platforms"] = deepcopy(profile.get("platforms") or cfg.get("platforms") or {})
    runtime_cfg["vertical_layout"] = deepcopy(profile.get("vertical_layout") or cfg.get("vertical_layout") or {})
    runtime_cfg.setdefault("review", {})["require_approval"] = profile.get("review_mode", "review") == "review"
    return runtime_cfg


def smart_highlight_window(
    source: Path, runtime_cfg: dict[str, Any], profile: dict[str, Any]
) -> tuple[float | None, float, str]:
    """Return a fail-soft highlight window with creator-friendly context."""
    target = float(profile.get("buffer_seconds") or 20)
    pre = max(0.0, min(30.0, float(profile.get("smart_pre_roll", 3.0))))
    post = max(0.0, min(30.0, float(profile.get("smart_post_roll", 2.0))))
    result = suggest_highlights_or_fallback(
        source, buffer_seconds=target, top_n=1, cfg=runtime_cfg
    )
    suggestion = (result.get("suggestions") or [{}])[0]
    start = suggestion.get("start")
    duration = float(suggestion.get("duration") or target)
    if start is None:
        # The pipeline's start=None behavior intentionally means "last N seconds".
        return None, target + pre + post, str(result.get("message") or "Used safe fallback.")
    start = max(0.0, float(start) - pre)
    duration = max(1.0, duration + pre + post)
    score = float(suggestion.get("score") or 0.0)
    note = f"Smart Highlight selected a {duration:.1f}s window"
    if score:
        note += f" (confidence {score:.0%})"
    return start, duration, note


def make_profile_file_handler(cfg: dict[str, Any], profile: dict[str, Any]):
    """Process a completed file that appeared in this profile's watch folder."""
    runtime_cfg = profile_runtime_cfg(cfg, profile)
    source_mode = str(profile.get("source_mode") or "last_seconds")
    seconds = int(profile.get("buffer_seconds") or 30)

    def _process(source: Path) -> None:
        start = None
        if source_mode == "smart_highlight":
            start, duration, _note = smart_highlight_window(source, runtime_cfg, profile)
        else:
            duration = None if source_mode == "whole_file" else float(seconds)
        run_pipeline(
            source,
            runtime_cfg,
            dry_run=bool((runtime_cfg.get("review") or {}).get("require_approval", True)),
            start=start,
            duration=duration,
        )

    return _process


def ensure_profile_watcher(
    holder: dict[str, Any], cfg: dict[str, Any], profile: dict[str, Any]
) -> FolderWatcher:
    """Create or refresh the automatic folder watcher for one profile."""
    watchers = holder.setdefault("profiles", {})
    profile_id = str(profile["id"])
    desired_folder = Path(str(profile.get("folder") or ""))
    existing = watchers.get(profile_id)
    if existing and getattr(existing, "folder", None) != desired_folder:
        existing.stop()
        existing = None
    if existing is None:
        existing = FolderWatcher(
            desired_folder,
            make_profile_file_handler(cfg, profile),
        )
        watchers[profile_id] = existing
    return existing


def stop_profile_watcher(holder: dict[str, Any], profile_id: str) -> None:
    watcher = (holder.get("profiles") or {}).pop(profile_id, None)
    if watcher:
        watcher.stop()


def register_live_routes(app, cfg: dict[str, Any], holder: dict) -> None:
    """Attach /live/status|start|stop JSON endpoints."""
    from fastapi.responses import JSONResponse

    from subscript.buffer import resolve_live_source as _resolve

    @app.get("/live/status")
    def live_status() -> JSONResponse:
        w = holder["w"]
        data = w.status() if w else {
            "armed": False,
            "hotkey": cfg.get("hotkey") or "ctrl+shift+c",
            "combo": "",
            "notify": bool(cfg.get("notify", True)),
            "fire_count": 0,
            "last_error": None,
            "last_ok": None,
        }
        data["source_hint"] = source_hint(cfg)
        data["buffer_seconds"] = int(cfg.get("buffer_seconds") or 30)
        data["auto_enqueue"] = bool(cfg.get("auto_enqueue", True))
        return JSONResponse(data)

    @app.post("/live/start")
    def live_start() -> JSONResponse:
        try:
            try:
                _resolve(cfg)
            except FileNotFoundError as exc:
                return JSONResponse(
                    {
                        "armed": False,
                        "hotkey": cfg.get("hotkey") or "ctrl+shift+c",
                        "last_error": str(exc),
                        "source_hint": source_hint(cfg),
                    },
                    status_code=400,
                )
            w = ensure_watcher(holder, cfg)
            w.start()
            data = w.status()
            data["source_hint"] = source_hint(cfg)
            return JSONResponse(data)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "armed": False,
                    "hotkey": cfg.get("hotkey") or "ctrl+shift+c",
                    "last_error": str(exc),
                    "source_hint": source_hint(cfg),
                },
                status_code=500,
            )

    @app.post("/live/stop")
    def live_stop() -> JSONResponse:
        w = holder["w"]
        if w:
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass
        data = w.status() if w else {"armed": False}
        data["source_hint"] = source_hint(cfg)
        data["hotkey"] = cfg.get("hotkey") or "ctrl+shift+c"
        return JSONResponse(data)
