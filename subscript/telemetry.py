"""Local-first telemetry, diagnostics, and support bundle helpers."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from subscript import __version__

_SECRET_KEY_RE = re.compile(
    r"(secret|token|password|passwd|api[_-]?key|authorization|cookie|credential)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/]+=*")
_LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9])")
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:code|token|access_token|refresh_token|client_secret|state|password)=)[^&\\s]+")

_LOGGER_NAME = "subscript"
_state_lock = threading.Lock()
_state: dict[str, Any] = {
    "session_id": None,
    "started_at": None,
    "log_dir": None,
    "heartbeat_stop": None,
    "heartbeat_thread": None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact_text(value: Any) -> str:
    text = str(value)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _QUERY_SECRET_RE.sub(lambda match: match.group(1) + "[REDACTED]", text)
    text = _LONG_TOKEN_RE.sub("[REDACTED]", text)
    return text


def redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_mapping(item)
        return out
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, tuple):
        return [redact_mapping(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": utc_now(),
            "level": record.levelname,
            "logger": record.name,
            "thread": record.threadName,
            "message": redact_text(record.getMessage()),
            "session_id": _state.get("session_id"),
        }
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        extra = getattr(record, "telemetry", None)
        if isinstance(extra, dict):
            payload.update(redact_mapping(extra))
        return json.dumps(payload, ensure_ascii=False, default=str)


def default_log_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "SubScript" / "logs"
    return Path("out") / "logs"


def configure_telemetry(log_dir: Path | None = None) -> Path:
    """Configure process-wide rotating logs once and return the log directory."""
    with _state_lock:
        if _state.get("log_dir"):
            return Path(_state["log_dir"])

        directory = Path(log_dir or default_log_dir())
        directory.mkdir(parents=True, exist_ok=True)
        _state["session_id"] = uuid.uuid4().hex[:12]
        _state["started_at"] = utc_now()
        _state["log_dir"] = str(directory)

        logger = logging.getLogger(_LOGGER_NAME)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        handler = RotatingFileHandler(
            directory / "subscript.jsonl",
            maxBytes=8 * 1024 * 1024,
            backupCount=8,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(JsonLineFormatter())
        logger.addHandler(handler)

        error_handler = RotatingFileHandler(
            directory / "errors.jsonl",
            maxBytes=4 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JsonLineFormatter())
        logger.addHandler(error_handler)

        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.addHandler(error_handler)

        original_excepthook = sys.excepthook
        def _sys_excepthook(exc_type, exc_value, exc_tb):
            logging.getLogger(_LOGGER_NAME).error(
                "Uncaught exception",
                exc_info=(exc_type, exc_value, exc_tb),
                extra={"telemetry": {"event": "uncaught_exception"}},
            )
            original_excepthook(exc_type, exc_value, exc_tb)
        sys.excepthook = _sys_excepthook

        original_thread_hook = getattr(threading, "excepthook", None)
        if original_thread_hook is not None:
            def _thread_excepthook(args):
                logging.getLogger(_LOGGER_NAME).error(
                    "Uncaught thread exception",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                    extra={"telemetry": {"event": "uncaught_thread_exception", "thread_name": getattr(args.thread, "name", "")}},
                )
                original_thread_hook(args)
            threading.excepthook = _thread_excepthook

        logger.info(
            "SubScript telemetry started",
            extra={"telemetry": {
                "event": "app_start",
                "version": __version__,
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "pid": os.getpid(),
            }},
        )
        return directory


def log_event(event: str, message: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.log(level, message, extra={"telemetry": {"event": event, **redact_mapping(fields)}})


def start_heartbeat(status_provider=None, interval: float = 1.0) -> None:
    """Write a lightweight heartbeat every second while the app is alive."""
    configure_telemetry()
    with _state_lock:
        thread = _state.get("heartbeat_thread")
        if thread and thread.is_alive():
            return
        stop = threading.Event()
        _state["heartbeat_stop"] = stop

        def run() -> None:
            while not stop.wait(max(0.5, float(interval))):
                fields: dict[str, Any] = {
                    "uptime_seconds": round(time.monotonic() - started_monotonic, 3),
                }
                if status_provider:
                    try:
                        provided = status_provider()
                        if isinstance(provided, dict):
                            fields.update(redact_mapping(provided))
                    except Exception as exc:  # noqa: BLE001
                        fields["status_error"] = str(exc)
                log_event("heartbeat", "App heartbeat", level=logging.DEBUG, **fields)

        started_monotonic = time.monotonic()
        thread = threading.Thread(target=run, name="subscript-telemetry", daemon=True)
        _state["heartbeat_thread"] = thread
        thread.start()


def stop_heartbeat() -> None:
    stop = _state.get("heartbeat_stop")
    if stop:
        stop.set()
    log_event("app_stop", "SubScript telemetry stopping")


def telemetry_info() -> dict[str, Any]:
    directory = configure_telemetry()
    return {
        "session_id": _state.get("session_id"),
        "started_at": _state.get("started_at"),
        "log_dir": str(directory),
        "version": __version__,
    }


def _safe_config(cfg: dict[str, Any]) -> dict[str, Any]:
    safe = redact_mapping(cfg)
    # Avoid shipping local absolute paths unless they are useful folder labels.
    if isinstance(safe, dict):
        safe.pop("oauth", None)
    return safe


def create_support_bundle(
    cfg: dict[str, Any],
    *,
    destination_dir: Path | None = None,
    extra_status: dict[str, Any] | None = None,
) -> Path:
    """Create a redacted ZIP suitable for attaching to a support issue."""
    log_dir = configure_telemetry()
    out = Path(destination_dir or (log_dir.parent / "support-bundles"))
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_id = str(_state.get("session_id") or "session")
    bundle = out / f"SubScript-Support-{stamp}-{session_id}.zip"

    manifest = {
        "created_at": utc_now(),
        "session_id": session_id,
        "version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "pid": os.getpid(),
        "cwd": str(Path.cwd()),
        "status": redact_mapping(extra_status or {}),
    }

    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("diagnostics/manifest.json", json.dumps(manifest, indent=2, default=str))
        zf.writestr("diagnostics/config.redacted.json", json.dumps(_safe_config(cfg), indent=2, default=str))
        zf.writestr(
            "README.txt",
            "SubScript support bundle\n"
            "Generated locally. Secrets/tokens are redacted where detectable.\n"
            "Review the archive before sharing if it may contain private filenames or paths.\n"
            "Repository: https://github.com/SensoredRooster/sub-script\n"
            "Issues: https://github.com/SensoredRooster/sub-script/issues\n",
        )
        for path in sorted(log_dir.glob("*.jsonl*")):
            if path.is_file():
                zf.write(path, arcname=f"logs/{path.name}")
    log_event("support_bundle_created", "Support bundle created", bundle=str(bundle))
    return bundle


def open_in_file_browser(path: Path) -> None:
    path = Path(path)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", str(path)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(path)])
