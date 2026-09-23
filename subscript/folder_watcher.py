"""Reliable polling watcher for completed video files dropped into a folder."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from subscript.buffer import _VIDEO_SUFFIXES
from subscript.telemetry import log_event

log = logging.getLogger("subscript.folder_watcher")


class FolderWatcher:
    """Watch one folder and process each new completed video once.

    The watcher snapshots existing files when it starts, so activating a profile
    does not unexpectedly process old recordings. New files must remain the same
    size and modification time across multiple polls before they are considered
    complete. Processing is sequential, which naturally queues bursts of files.
    """

    def __init__(
        self,
        folder: Path,
        on_file: Callable[[Path], None],
        *,
        poll_seconds: float = 1.0,
        stable_polls: int = 2,
    ) -> None:
        self.folder = Path(folder)
        self._on_file = on_file
        self.poll_seconds = max(0.25, float(poll_seconds))
        self.stable_polls = max(2, int(stable_polls))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._armed = False
        self._lock = threading.Lock()
        self._seen: set[tuple[str, int, int]] = set()
        self._pending: dict[Path, tuple[int, int, int]] = {}
        self.last_error: str | None = None
        self.last_ok: str | None = None
        self.fire_count = 0

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def hotkey_spec(self) -> str:
        # Compatibility attribute for older UI/tests that inspected watchers.
        return ""

    def _signature(self, path: Path) -> tuple[str, int, int] | None:
        try:
            stat = path.stat()
            if stat.st_size <= 0:
                return None
            return (str(path.resolve()).lower(), int(stat.st_size), int(stat.st_mtime_ns))
        except OSError:
            return None

    def _video_files(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        items = []
        try:
            for path in self.folder.iterdir():
                if not path.is_file() or path.suffix.lower() not in _VIDEO_SUFFIXES:
                    continue
                if path.name.lower().endswith((".tmp", ".part", ".partial")):
                    continue
                items.append(path)
        except OSError:
            return []
        return sorted(items, key=lambda p: p.name.lower())

    def _snapshot_existing(self) -> None:
        self._seen.clear()
        for path in self._video_files():
            signature = self._signature(path)
            if signature:
                self._seen.add(signature)

    def _ready(self, path: Path) -> bool:
        signature = self._signature(path)
        if signature is None or signature in self._seen:
            self._pending.pop(path, None)
            return False
        _key, size, mtime = signature
        previous = self._pending.get(path)
        if previous and previous[0] == size and previous[1] == mtime:
            stable = previous[2] + 1
        else:
            stable = 1
        self._pending[path] = (size, mtime, stable)
        if stable < self.stable_polls:
            return False
        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError:
            return False
        return True

    def _run(self) -> None:
        try:
            if not self.folder.is_dir():
                raise FileNotFoundError(f"Watch folder not found: {self.folder}")
            self._snapshot_existing()
            self._armed = True
            self.last_error = None
            self.last_ok = f"Watching for new videos in {self.folder}"
            log_event("watcher_started", "Folder watcher started", folder=str(self.folder))
            while not self._stop.wait(self.poll_seconds):
                if not self.folder.is_dir():
                    self.last_error = f"Watch folder is unavailable: {self.folder}"
                    continue
                for path in self._video_files():
                    if not self._ready(path):
                        continue
                    signature = self._signature(path)
                    if signature is None:
                        continue
                    try:
                        self.last_ok = f"New clip detected: {path.name}"
                        log_event("watcher_file_detected", "New completed video detected", file_name=path.name, folder=str(self.folder))
                        self._on_file(path)
                        self.fire_count += 1
                        self.last_error = None
                        self.last_ok = f"Processed {path.name}"
                        log_event("watcher_file_processed", "Watched video processed", file_name=path.name, folder=str(self.folder))
                        self._seen.add(signature)
                    except Exception as exc:  # noqa: BLE001
                        self.last_error = f"{path.name}: {exc}"
                        log_event("watcher_file_failed", "Watched video processing failed", level=logging.ERROR, file_name=path.name, error=str(exc))
                        log.exception("Automatic folder processing failed")
                        # Mark this exact file version as seen so a permanent
                        # render error does not create an infinite retry loop.
                        self._seen.add(signature)
                    finally:
                        self._pending.pop(path, None)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Watcher failed to start: {exc}"
            log.exception("Folder watcher crashed")
        finally:
            self._armed = False

    def start(self) -> None:
        with self._lock:
            if self._armed or (self._thread and self._thread.is_alive()):
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name=f"subscript-folder-{self.folder.name}",
                daemon=True,
            )
            self._thread.start()
        for _ in range(20):
            if self._armed or self.last_error:
                break
            time.sleep(0.05)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.poll_seconds * 2))
        self._armed = False
        log_event("watcher_stopped", "Folder watcher stopped", folder=str(self.folder))

    def status(self) -> dict:
        return {
            "armed": self._armed,
            "folder": str(self.folder),
            "fire_count": self.fire_count,
            "last_error": self.last_error,
            "last_ok": self.last_ok,
        }
