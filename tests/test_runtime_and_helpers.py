"""Sidecar tool discovery (ffmpeg / ffprobe beside the app) and misc helpers."""

from __future__ import annotations

from pathlib import Path

from subscript import runtime_paths as rp
from subscript.default_brand import ensure_default_logo
from subscript.hotkey import HotkeyWatcher, parse_hotkey

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_app_dir_and_resource_dir_from_source() -> None:
    assert rp.is_frozen() is False
    assert rp.app_dir() == REPO_ROOT
    assert rp.resource_dir() == REPO_ROOT
    assert "ffmpeg.exe" in rp.ffmpeg_install_hint()


def test_find_tools_beside_app(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "ffmpeg.exe").write_bytes(b"x")
    (tmp_path / "ffprobe.exe").write_bytes(b"x")
    monkeypatch.setattr(rp, "app_dir", lambda: tmp_path)
    assert Path(rp.find_ffmpeg()) == (tmp_path / "ffmpeg.exe").resolve()
    assert Path(rp.find_ffprobe()) == (tmp_path / "ffprobe.exe").resolve()


def test_find_tools_in_bin_subfolder(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "ffmpeg" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ffmpeg.exe").write_bytes(b"x")
    (bin_dir / "ffprobe.exe").write_bytes(b"x")
    monkeypatch.setattr(rp, "app_dir", lambda: tmp_path)
    assert Path(rp.find_ffmpeg()) == (bin_dir / "ffmpeg.exe").resolve()
    assert Path(rp.find_ffprobe()) == (bin_dir / "ffprobe.exe").resolve()


def test_find_ffprobe_uses_sibling_basename_only(tmp_path: Path, monkeypatch) -> None:
    empty_app = tmp_path / "app"
    empty_app.mkdir()
    monkeypatch.setattr(rp, "app_dir", lambda: empty_app)
    # Directory name also contains "ffmpeg" — only the file name may be swapped.
    bin_dir = tmp_path / "ffmpeg-7.1-essentials" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ffmpeg.exe").write_bytes(b"x")
    (bin_dir / "ffprobe.exe").write_bytes(b"x")
    got = rp.find_ffprobe(str(bin_dir / "ffmpeg.exe"))
    assert Path(got) == (bin_dir / "ffprobe.exe").resolve()


def test_find_ffprobe_falls_back_to_path(tmp_path: Path, monkeypatch) -> None:
    empty_app = tmp_path / "app"
    empty_app.mkdir()
    monkeypatch.setattr(rp, "app_dir", lambda: empty_app)
    monkeypatch.setattr(rp.shutil, "which", lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None)
    assert rp.find_ffprobe("/nowhere/ffmpeg") == "/usr/bin/ffprobe"
    assert rp.find_ffmpeg() is None


def test_parse_hotkey_maps_modifiers() -> None:
    assert parse_hotkey("ctrl+shift+c") == "<ctrl>+<shift>+c"
    assert parse_hotkey("Alt + F9") == "<alt>+f9"
    assert parse_hotkey("win+x") == "<cmd>+x"
    assert parse_hotkey("control+option+z") == "<ctrl>+<alt>+z"


def test_hotkey_watcher_status_before_start() -> None:
    w = HotkeyWatcher("ctrl+shift+c", lambda: None, notify=False)
    status = w.status()
    assert status["armed"] is False and status["combo"] == "<ctrl>+<shift>+c"
    assert status["fire_count"] == 0 and status["last_error"] is None
    w.stop()  # idempotent when never started


def test_ensure_default_logo_writes_valid_png(tmp_path: Path) -> None:
    logo = ensure_default_logo(tmp_path)
    assert logo == tmp_path / "assets" / "logo.png"
    data = logo.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data.rstrip().endswith(b"IEND\xaeB`\x82")
    # Existing non-empty logo is left alone.
    logo.write_bytes(b"custom")
    assert ensure_default_logo(tmp_path).read_bytes() == b"custom"
