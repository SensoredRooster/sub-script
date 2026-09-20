"""Time parsing shared by the CLI and the app form, plus live-source resolution."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pytest

from subscript.buffer import BufferSource, newest_video_in, resolve_live_source
from subscript.cli import parse_time
from subscript.live_app import _parse_time_field


@pytest.mark.parametrize(
    ("text", "expected"),
    [("90", 90.0), ("1:30", 90.0), ("01:02:03", 3723.0), ("1:02:03.5", 3723.5), (" 5 ", 5.0)],
)
def test_parse_time_variants(text: str, expected: float) -> None:
    assert parse_time(text) == expected
    assert _parse_time_field(text) == expected


@pytest.mark.parametrize("bad", ["", "abc", "1:2:3:4", "1:xx"])
def test_parse_time_rejects_garbage(bad: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_time(bad)


def test_parse_time_field_blank_is_none() -> None:
    assert _parse_time_field(None) is None
    assert _parse_time_field("   ") is None
    with pytest.raises(ValueError):
        _parse_time_field("nope")


def test_newest_video_in_ignores_non_video(tmp_path: Path) -> None:
    older = tmp_path / "old.mp4"
    newer = tmp_path / "new.mkv"
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    older.write_bytes(b"o")
    newer.write_bytes(b"n")
    past = time.time() - 500
    os.utime(older, (past, past))
    assert newest_video_in(tmp_path) == newer
    assert newest_video_in(tmp_path / "missing") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert newest_video_in(empty) is None


def test_resolve_live_source_precedence(tmp_path: Path) -> None:
    folder = tmp_path / "obs"
    folder.mkdir()
    clip = folder / "Replay.mp4"
    clip.write_bytes(b"x")
    override = tmp_path / "override.mp4"
    override.write_bytes(b"y")

    assert resolve_live_source({"live_source": str(clip)}, override) == override
    assert resolve_live_source({"live_source": str(clip)}) == clip
    assert resolve_live_source({"live_source": "", "watch_folder": str(folder)}) == clip
    # A folder given as live_source picks the newest video inside it.
    assert resolve_live_source({"live_source": str(folder)}) == clip


def test_resolve_live_source_errors_are_actionable(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No live source configured"):
        resolve_live_source({})
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="watch_folder"):
        resolve_live_source({"watch_folder": str(empty)})
    with pytest.raises(FileNotFoundError, match="not found"):
        BufferSource(path=tmp_path / "nope.mp4").resolve()
