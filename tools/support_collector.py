"""Optional SubScript support-bundle collector.

Run on infrastructure you control. This service is NOT started by SubScript.

Environment:
  SUBSCRIPT_SUPPORT_COLLECTOR_TOKEN=<long-random-secret>
  SUBSCRIPT_SUPPORT_INBOX=/path/to/support-inbox   (optional)

Run:
  uvicorn tools.support_collector:app --host 0.0.0.0 --port 8790
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="SubScript Support Collector")

MAX_BUNDLE_BYTES = 50 * 1024 * 1024
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _token() -> str:
    value = os.getenv("SUBSCRIPT_SUPPORT_COLLECTOR_TOKEN", "").strip()
    if not value:
        raise RuntimeError("SUBSCRIPT_SUPPORT_COLLECTOR_TOKEN is required.")
    return value


def _inbox() -> Path:
    path = Path(os.getenv("SUBSCRIPT_SUPPORT_INBOX", "support-inbox")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _authorize(authorization: str | None) -> None:
    expected = "Bearer " + _token()
    if not authorization or authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid support collector token.")


def _safe_name(value: str, fallback: str) -> str:
    cleaned = _SAFE.sub("-", value.strip()).strip(".-")
    return cleaned[:120] or fallback


@app.get("/health")
def health() -> dict:
    # Health intentionally does not disclose inbox contents.
    return {"ok": True, "service": "subscript-support-collector"}


@app.post("/upload")
async def upload(
    request: Request,
    authorization: str | None = Header(default=None),
    x_subscript_session: str | None = Header(default=None),
    x_subscript_version: str | None = Header(default=None),
    x_subscript_filename: str | None = Header(default=None),
):
    _authorize(authorization)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BUNDLE_BYTES:
                raise HTTPException(status_code=413, detail="Support bundle is too large.")
        except ValueError:
            pass

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty support bundle.")
    if len(data) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="Support bundle is too large.")
    if not data.startswith(b"PK"):
        raise HTTPException(status_code=415, detail="Expected a ZIP support bundle.")

    session = _safe_name(x_subscript_session or "", "unknown-session")
    version = _safe_name(x_subscript_version or "", "unknown-version")
    original = _safe_name(x_subscript_filename or "", "SubScript-Support.zip")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{stamp}-{session}-{original}"
    path = _inbox() / name
    path.write_bytes(data)

    metadata = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session,
        "version": version,
        "bundle": name,
        "size_bytes": len(data),
        "client": request.client.host if request.client else None,
    }
    path.with_suffix(path.suffix + ".json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    return JSONResponse({"ok": True, "bundle": name, "session_id": session})


@app.get("/bundles")
def list_bundles(authorization: str | None = Header(default=None)):
    _authorize(authorization)
    items = []
    for path in sorted(_inbox().glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta_path = path.with_suffix(path.suffix + ".json")
        metadata = {}
        if meta_path.is_file():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        items.append({
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            **metadata,
        })
    return {"bundles": items}


@app.get("/bundles/{bundle_name}")
def download_bundle(bundle_name: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    safe = _safe_name(bundle_name, "")
    if safe != bundle_name or not safe.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Invalid bundle name.")
    path = _inbox() / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Bundle not found.")
    return FileResponse(path, media_type="application/zip", filename=path.name)
