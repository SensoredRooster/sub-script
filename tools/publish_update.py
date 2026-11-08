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
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subscript import __version__  # noqa: E402

FEED = os.getenv(
    "SUBSCRIPT_UPDATE_FEED",
    "https://subscript-updates.sensoredrooster-com.workers.dev",
).rstrip("/")
USER_AGENT = f"SubScript-Release/{__version__}"  # a bare urllib UA is blocked at the edge


def _put(key: str, data: bytes, content_type: str, token: str) -> None:
    req = urllib.request.Request(
        f"{FEED}/{key}",
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=280) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"PUT {key} failed: HTTP {exc.code} {exc.read()[:300]!r}") from exc
    print(f"PUT {key}: {body}")


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
