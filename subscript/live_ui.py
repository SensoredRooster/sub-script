"""Live hotkey helpers for the review app UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from subscript.buffer import newest_video_in, resolve_live_source
from subscript.hotkey import HotkeyWatcher
from subscript.pipeline import run_pipeline


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
        auto_enqueue = bool(cfg.get("auto_enqueue", True))
        source = resolve_live_source(cfg)
        live_cfg = dict(cfg)
        if auto_enqueue:
            review = dict(live_cfg.get("review") or {})
            review["require_approval"] = True
            live_cfg["review"] = review
        run_pipeline(
            source,
            live_cfg,
            dry_run=True,
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
