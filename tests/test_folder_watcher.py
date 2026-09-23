import time
from pathlib import Path

from subscript.folder_watcher import FolderWatcher


def _wait_until(predicate, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_folder_watcher_ignores_existing_and_processes_new_completed_video(tmp_path: Path):
    existing = tmp_path / "old.mp4"
    existing.write_bytes(b"old")

    processed = []
    watcher = FolderWatcher(tmp_path, processed.append, poll_seconds=0.05, stable_polls=2)
    watcher.start()
    try:
        assert watcher.armed is True
        time.sleep(0.15)
        assert processed == []

        incoming = tmp_path / "new.mp4"
        incoming.write_bytes(b"new-video")
        assert _wait_until(lambda: processed == [incoming])
        assert watcher.fire_count == 1
        assert watcher.last_error is None
    finally:
        watcher.stop()


def test_folder_watcher_waits_for_file_to_stabilize(tmp_path: Path):
    processed = []
    watcher = FolderWatcher(tmp_path, processed.append, poll_seconds=0.05, stable_polls=3)
    watcher.start()
    try:
        incoming = tmp_path / "growing.mp4"
        incoming.write_bytes(b"a")
        time.sleep(0.06)
        incoming.write_bytes(b"abcdef")
        time.sleep(0.06)
        assert processed == []
        assert _wait_until(lambda: processed == [incoming])
    finally:
        watcher.stop()


def test_folder_watcher_ignores_unsupported_files(tmp_path: Path):
    processed = []
    watcher = FolderWatcher(tmp_path, processed.append, poll_seconds=0.05)
    watcher.start()
    try:
        (tmp_path / "notes.txt").write_text("not a video", encoding="utf-8")
        time.sleep(0.2)
        assert processed == []
    finally:
        watcher.stop()
