"""Small authentication boundary for local development and future accounts.

This intentionally does not pretend that a social provider is an identity provider
for SubScript. Production account authentication can be added behind this boundary
without touching publishing OAuth connections.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse


SESSION_COOKIE = "subscript_session"


def required(cfg: dict[str, Any]) -> bool:
    return bool((cfg.get("auth") or {}).get("required", False))


def is_authenticated(request: Request, cfg: dict[str, Any]) -> bool:
    if not required(cfg):
        return True
    return request.cookies.get(SESSION_COOKIE) == "local"


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    response = RedirectResponse("/login?next=" + target, status_code=303)
    return response
