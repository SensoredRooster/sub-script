"""Software-update check and install endpoints for the Windows app."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from subscript import app_update
from subscript.auth import is_authenticated


def register_update_routes(app, cfg: dict) -> None:
    @app.get("/update/status")
    def update_status(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"detail": "Sign in required."}, status_code=401)
        return JSONResponse(app_update.service.check())

    @app.post("/update/install")
    def update_install(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"detail": "Sign in required."}, status_code=401)
        try:
            return JSONResponse(app_update.service.start_install())
        except app_update.UpdateError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/update/job")
    def update_job(request: Request):
        if not is_authenticated(request, cfg):
            return JSONResponse({"detail": "Sign in required."}, status_code=401)
        return JSONResponse(app_update.service.job())
