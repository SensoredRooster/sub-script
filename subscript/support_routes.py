"""Tester support center, support bundle export, and repo routing."""

from __future__ import annotations

from html import escape
from pathlib import Path
import os
import urllib.request
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from subscript.auth import is_authenticated, login_redirect
from subscript.telemetry import (
    create_support_bundle,
    open_in_file_browser,
    telemetry_info,
)

_REPO = "https://github.com/SensoredRooster/sub-script"
_ISSUES = _REPO + "/issues/new"


def _watcher_status(holder: dict) -> dict:
    profiles = holder.get("profiles") or {}
    return {
        "global_watcher": bool(holder.get("w") and getattr(holder["w"], "armed", False)),
        "profile_watchers": {
            str(key): {
                "armed": bool(getattr(watcher, "armed", False)),
                "last_error": getattr(watcher, "last_error", None),
                "last_ok": getattr(watcher, "last_ok", None),
                "fire_count": getattr(watcher, "fire_count", 0),
            }
            for key, watcher in profiles.items()
        },
    }


def register_support_routes(app, cfg: dict, holder: dict, snip) -> None:
    @app.get("/support", response_class=HTMLResponse)
    def support_center(request: Request):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        info = telemetry_info()
        template = snip("support.html")
        support_cfg = cfg.get("support") if isinstance(cfg.get("support"), dict) else {}
        upload_url = os.getenv("SUBSCRIPT_SUPPORT_UPLOAD_URL") or str(support_cfg.get("upload_url") or "")
        upload_control = (
            '<button type="button" class="secondary" data-upload-support-bundle>Send Diagnostics to Developer</button>'
            if upload_url.strip()
            else '<span class="meta">Remote support upload is not configured on this build.</span>'
        )
        return (
            template
            .replace("{{SESSION_ID}}", escape(str(info.get("session_id") or "")))
            .replace("{{LOG_DIR}}", escape(str(info.get("log_dir") or "")))
            .replace("{{VERSION}}", escape(str(info.get("version") or "")))
            .replace("{{UPLOAD_CONTROL}}", upload_control)
        )

    @app.get("/support/status")
    def support_status(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"error": "Sign in required."}, status_code=401)
        return JSONResponse({**telemetry_info(), **_watcher_status(holder)})

    @app.post("/support/bundle")
    def support_bundle(request: Request):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        bundle = create_support_bundle(cfg, extra_status=_watcher_status(holder))
        return FileResponse(
            bundle,
            media_type="application/zip",
            filename=bundle.name,
        )

    @app.post("/support/upload")
    def upload_support_bundle(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"error": "Sign in required."}, status_code=401)
        support_cfg = cfg.get("support") if isinstance(cfg.get("support"), dict) else {}
        upload_url = os.getenv("SUBSCRIPT_SUPPORT_UPLOAD_URL") or str(support_cfg.get("upload_url") or "")
        if not upload_url.strip():
            return JSONResponse({"error": "Remote support upload is not configured."}, status_code=409)
        bundle = create_support_bundle(cfg, extra_status=_watcher_status(holder))
        data = bundle.read_bytes()
        headers = {
            "Content-Type": "application/zip",
            "X-SubScript-Session": str(telemetry_info().get("session_id") or ""),
            "X-SubScript-Version": str(telemetry_info().get("version") or ""),
            "X-SubScript-Filename": bundle.name,
        }
        upload_token = os.getenv("SUBSCRIPT_SUPPORT_UPLOAD_TOKEN", "").strip()
        if upload_token:
            headers["Authorization"] = "Bearer " + upload_token
        req = urllib.request.Request(
            upload_url.strip(),
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise RuntimeError(f"Support server returned HTTP {status}.")
            return JSONResponse({"ok": True, "message": "Diagnostics sent to developer.", "filename": bundle.name})
        except Exception as exc:
            return JSONResponse({"error": f"Could not send diagnostics: {exc}"}, status_code=502)

    @app.post("/support/open-logs")
    def open_logs(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"error": "Sign in required."}, status_code=401)
        folder = Path(telemetry_info()["log_dir"])
        try:
            open_in_file_browser(folder)
            return JSONResponse({"ok": True, "folder": str(folder)})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/support/repository")
    def repository():
        return RedirectResponse(_REPO, status_code=303)

    @app.get("/support/report")
    def report_issue(request: Request):
        if not is_authenticated(request, cfg):
            return login_redirect(request)
        info = telemetry_info()
        session_id = str(info.get("session_id") or "")
        version = str(info.get("version") or "")
        body = (
            "## What happened?\n\n"
            "Describe what you were doing and what you expected.\n\n"
            "## What actually happened?\n\n"
            "Describe the problem.\n\n"
            "## Diagnostics\n"
            f"- SubScript version: {version}\n"
            f"- Session ID: {session_id}\n\n"
            "Please attach the Support Bundle downloaded from SubScript > Support.\n"
            "Before uploading, review the ZIP if filenames or local paths are sensitive.\n"
        )
        url = _ISSUES + "?title=" + quote("Tester report: ") + "&body=" + quote(body)
        return RedirectResponse(url, status_code=303)
