"""Approve fan-out: local pack, manual handoff packs, fail-soft per platform, YouTube dry-run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subscript.publish import (
    PublishMeta,
    PublishResult,
    format_platform_banner,
    publish_local,
    run_enabled_publishers,
)
from subscript.publish.manual import manual_handoff
from subscript.publish.youtube import YouTubePublisher, youtube_live_enabled


@pytest.fixture(autouse=True)
def _no_explorer(monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_NO_OPEN", "1")
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")


def _meta(out: Path, item_id: str = "abc") -> PublishMeta:
    approved = out / "approved" / item_id
    approved.mkdir(parents=True, exist_ok=True)
    return PublishMeta(item_id=item_id, title="Highlight", out_dir=out, approved_dir=approved)


def test_publish_local_builds_pack(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    h = out / "clip-horizontal-x.mp4"
    v = out / "clip-vertical-x.mp4"
    c = out / "clip-vertical-captioned-x.mp4"
    m = out / "clip-branded-x.mp4"
    for p in (h, v, c, m):
        p.write_bytes(b"\x00" * 16)
    meta = publish_local(item_id="abc", title="T", out_dir=out, horizontal=h, vertical=v, vertical_captioned=c, master=m)
    approved = out / "approved" / "abc"
    for name in ("horizontal.mp4", "vertical.mp4", "vertical_captioned.mp4", "master.mp4", "PLATFORMS.txt", "manifest.json"):
        assert (approved / name).is_file(), name
    manifest = json.loads((approved / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["item_id"] == "abc" and len(manifest["files"]) == 5
    assert "TikTok" in (approved / "PLATFORMS.txt").read_text(encoding="utf-8")
    assert meta["title"] == "T"


def test_publish_local_skips_missing_inputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    meta = publish_local(item_id="x", title="T", out_dir=out, horizontal=out / "missing.mp4")
    assert [Path(f).name for f in meta["files"]] == ["PLATFORMS.txt"]


def test_run_enabled_publishers_is_fail_soft(tmp_path: Path) -> None:
    out = tmp_path / "out"
    meta = _meta(out)
    video = out / "clip-vertical-captioned-x.mp4"
    video.write_bytes(b"v")
    cfg = {
        "youtube": {"enabled": False},
        "platforms": {
            "tiktok": {"enabled": True, "mode": "manual"},
            "twitter": {"enabled": True, "mode": "api"},
            "rumble": {"enabled": False},
        },
    }
    results = run_enabled_publishers(video, meta, cfg, out)
    by = {r.platform: r for r in results}
    assert set(by) == {"TikTok", "Twitter"}
    assert by["TikTok"].ok and by["TikTok"].status == "manual"
    assert (meta.approved_dir / "for_tiktok" / "vertical_captioned.mp4").is_file()
    assert (meta.approved_dir / "for_tiktok" / "POST_INSTRUCTIONS.txt").is_file()
    assert not by["Twitter"].ok and by["Twitter"].status == "not_configured"
    banner = format_platform_banner(results)
    assert "TikTok: manual" in banner and "Twitter: not_configured" in banner


def test_run_enabled_publishers_reports_missing_video(tmp_path: Path) -> None:
    out = tmp_path / "out"
    meta = _meta(out)
    cfg = {"platforms": {"facebook": {"enabled": True}}}
    results = run_enabled_publishers(out / "nope.mp4", meta, cfg, out)
    assert len(results) == 1 and results[0].status == "error" and not results[0].ok


def test_format_platform_banner_empty() -> None:
    assert "No platforms enabled" in format_platform_banner([])
    r = PublishResult(platform="YouTube", ok=True, status="uploaded", url="https://youtu.be/x")
    assert format_platform_banner([r]) == "YouTube: uploaded — https://youtu.be/x"


def test_manual_handoff_names_by_variant(tmp_path: Path) -> None:
    out = tmp_path / "out"
    meta = _meta(out)
    for src_name, expect in (
        ("clip-horizontal-1.mp4", "horizontal.mp4"),
        ("clip-vertical-1.mp4", "vertical.mp4"),
        ("clip-vertical-captioned-1.mp4", "vertical_captioned.mp4"),
        ("weird.mov", "vertical_captioned.mov"),
    ):
        src = out / src_name
        src.write_bytes(b"x")
        res = manual_handoff(platform_key="rumble", display_name="Rumble", path=src, meta=meta, instructions="do it")
        assert res.ok and Path(res.detail["video"]).name == expect


def test_youtube_live_enabled_switches() -> None:
    assert youtube_live_enabled({}) is False
    assert youtube_live_enabled({"youtube": {"enabled": True}}) is True
    assert youtube_live_enabled({"platforms": {"youtube": {"enabled": True}}}) is True


def test_youtube_publisher_dry_run_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "out"
    meta = _meta(out)
    video = out / "clip-vertical-captioned-x.mp4"
    video.write_bytes(b"v")
    pub = YouTubePublisher({"youtube": {"enabled": False, "title_template": "Hi {timestamp}"}}, out)
    assert pub.enabled is False
    res = pub.publish(video, meta)
    assert res.ok and res.status == "dry_run"
    assert res.detail["title"].startswith("Hi ")
    assert "#Shorts" in res.detail["description"]
    assert list(out.glob("upload-dry-run-*.json"))
