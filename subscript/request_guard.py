"""Block cross-site browser requests from changing local SubScript state (CSRF guard).

The studio listens on loopback, but any web page open in the user's browser can still
submit a form or fetch() to http://127.0.0.1:<port>. Browsers label such requests with
``Sec-Fetch-Site: cross-site`` and an ``Origin`` header, so state-changing requests that
carry either signal from a non-local origin are rejected. Non-browser clients (CLI,
the local production bridge, tests) send neither header and are unaffected.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _origin_is_local(origin: str, request_host: str) -> bool:
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False
    if parts.hostname in LOOPBACK_HOSTS:
        return True
    # Allow the exact host the app is served on (e.g. a configured LAN address).
    return bool(request_host) and parts.netloc.lower() == request_host.lower()


def is_cross_site_write(method: str, headers: dict[str, str] | object, request_host: str = "") -> bool:
    """Return True when a state-changing request comes from a foreign web origin."""
    if method.upper() in SAFE_METHODS:
        return False
    get = headers.get  # type: ignore[attr-defined]
    fetch_site = str(get("sec-fetch-site") or "").strip().lower()
    if fetch_site == "cross-site":
        return True
    origin = str(get("origin") or "").strip()
    if origin:
        return not _origin_is_local(origin, request_host)
    return False


def install_request_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def cross_site_write_guard(request: Request, call_next):
        if is_cross_site_write(request.method, request.headers, request.headers.get("host", "")):
            return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        return await call_next(request)
