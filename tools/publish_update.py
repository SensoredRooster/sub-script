"""Upload a signed installer + latest.json to the SubScript update feed.

Usage:
    python tools/publish_update.py path/to/SubScript-Setup-1.2.3.exe [--notes "What's new"]

Requires the SUBSCRIPT_UPLOAD_TOKEN environment variable (repository secret).
The feed is the Cloudflare updates worker; its R2 bucket keeps every installer
under releases/ and serves latest.json to the in-app updater.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript import __version__  # noqa: E402

FEED = os.getenv(
    "SUBSCRIPT_UPDATE_FEED",
    "https://subscript-updates.sensoredrooster-com.workers.dev",
).rstrip("/")
USER_AGENT = f"SubScript-Release/{__version__}"  # a bare urllib UA is blocked at the edge

# The edge rejects single requests above ~100 MB, so big installers go up in parts.
PART_SIZE = 16 * 1024 * 1024  # R2 multipart requires >=5 MiB per part except the last
PLAIN_PUT_LIMIT = 80 * 1024 * 1024


def _request(req: urllib.request.Request, timeout: int = 280) -> str:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"{req.method} {req.full_url} failed: HTTP {exc.code} {exc.read()[:300]!r}"
        ) from exc


def _call(
    key: str,
    method: str,
    token: str,
    data: bytes | None = None,
    params: str = "",
    content_type: str = "application/octet-stream",
) -> str:
    req = urllib.request.Request(
        f"{FEED}/{key}{params}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "User-Agent": USER_AGENT,
        },
    )
    return _request(req)


def _put(key: str, data: bytes, content_type: str, token: str) -> None:
    body = _call(key, "PUT", token, data=data, content_type=content_type)
    print(f"PUT {key}: {body}")


def _put_large(key: str, path: Path, content_type: str, token: str) -> None:
    """Chunked upload through the worker's R2 multipart endpoints."""
    created = json.loads(_call(key, "POST", token, params="?action=mpu-create", content_type=content_type))
    upload_id = created["uploadId"]
    qid = urllib.parse.quote(upload_id, safe="")
    parts: list[dict] = []
    try:
        with path.open("rb") as fh:
            num = 0
            while True:
                chunk = fh.read(PART_SIZE)
                if not chunk:
                    break
                num += 1
                info = json.loads(
                    _call(key, "PUT", token, data=chunk,
                          params=f"?action=mpu-part&uploadId={qid}&part={num}",
                          content_type=content_type)
                )
                parts.append({"partNumber": num, "etag": info["etag"]})
                print(f"  part {num}: {len(chunk)} bytes")
        body = _call(key, "POST", token,
                     data=json.dumps({"parts": parts}).encode("utf-8"),
                     params=f"?action=mpu-complete&uploadId={qid}",
                     content_type="application/json")
        print(f"PUT {key} (multipart, {len(parts)} parts): {body}")
    except BaseException:
        try:
            _call(key, "DELETE", token, params=f"?action=mpu-abort&uploadId={qid}")
        except SystemExit:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("--notes", default="", help="One-line release note for latest.json")
    args = parser.parse_args()

    token = os.getenv("SUBSCRIPT_UPLOAD_TOKEN", "").strip()
    if not token:
        raise SystemExit("SUBSCRIPT_UPLOAD_TOKEN is not set.")
    exe: Path = args.installer
    if not exe.is_file():
        raise SystemExit(f"Installer not found: {exe}")

    digest = hashlib.sha256()
    with exe.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    print(f"sha256: {sha}")

    if exe.stat().st_size > PLAIN_PUT_LIMIT:
        _put_large(f"releases/{exe.name}", exe, "application/octet-stream", token)
    else:
        _put(f"releases/{exe.name}", exe.read_bytes(), "application/octet-stream", token)

    latest = {
        "version": __version__,
        "url": f"{FEED}/releases/{exe.name}",
        "sha256": sha,
        "notes": args.notes,
    }
    _put("latest.json", json.dumps(latest).encode("utf-8"), "application/json", token)
    print(f"Published {__version__} to {FEED}")


if __name__ == "__main__":
    main()
