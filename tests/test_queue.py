"""Review queue persistence and legacy-item compatibility."""

from __future__ import annotations

from pathlib import Path

import pytest

from subscript.queue import QueueItem, ReviewQueue


def test_enqueue_list_get_and_status(tmp_path: Path) -> None:
    q = ReviewQueue(tmp_path / "q.json")
    a = q.enqueue(tmp_path / "a.mp4", tmp_path / "src.mp4", title="A")
    b = q.enqueue(
        tmp_path / "b.mp4",
        tmp_path / "src.mp4",
        horizontal_path=tmp_path / "h.mp4",
        vertical_path=tmp_path / "v.mp4",
        vertical_captioned_path=tmp_path / "c.mp4",
    )
    assert b.title == "b"  # falls back to the video stem
    ids = [i.id for i in q.list()]
    assert ids[0] == b.id and ids[1] == a.id  # newest first
    assert [i.id for i in q.list(status="pending")] == ids

    got = q.get(b.id)
    assert got is not None and got.vertical_captioned_path == str(tmp_path / "c.mp4")

    q.set_status(a.id, "rejected")
    assert q.get(a.id).status == "rejected"
    assert [i.id for i in q.list(status="pending")] == [b.id]

    updated = q.set_status(b.id, "pending", trim_start=1.0, trim_end=4.5, edited_path="e.mp4", bogus="x")
    assert updated.trim_start == 1.0 and updated.trim_end == 4.5 and updated.edited_path == "e.mp4"
    assert not hasattr(updated, "bogus")


def test_update_unknown_item_raises(tmp_path: Path) -> None:
    q = ReviewQueue(tmp_path / "q.json")
    with pytest.raises(KeyError):
        q.update(QueueItem(id="nope", video_path="v", source_path="s", created_at="t"))
    with pytest.raises(KeyError):
        q.set_status("nope", "approved")
    assert q.get("nope") is None


def test_from_dict_accepts_legacy_and_unknown_keys() -> None:
    legacy = {
        "id": "abc",
        "video_path": "out/x.mp4",
        "source_path": "src.mp4",
        "created_at": "2026-01-01T00:00:00+00:00",
        "status": "approved",
        "future_field": 123,
    }
    item = QueueItem.from_dict(legacy)
    assert item.id == "abc" and item.status == "approved"
    assert item.horizontal_path is None and item.vertical_captioned_path is None
    assert "future_field" not in item.to_dict()


def test_queue_file_is_created_and_reloaded(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "q.json"
    q = ReviewQueue(path)
    assert path.is_file()
    q.enqueue(tmp_path / "a.mp4", tmp_path / "s.mp4")
    again = ReviewQueue(path)
    assert len(again.list()) == 1
