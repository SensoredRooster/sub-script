"""ffmpeg-backed media steps: clip, brand, reframe, trim, music, and the full pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from subscript.brand import apply_brand, compose_brand_sequence
from subscript.clip import clip_last_seconds, run_ffmpeg
from subscript.music import maybe_mix_music, music_volume, resolve_music_path
from subscript.pipeline import run_pipeline
from subscript.queue import ReviewQueue
from subscript.reframe import make_social_pair
from subscript.trim import trim_clip
from tests.conftest import FFMPEG, needs_ffmpeg

pytestmark = needs_ffmpeg


def test_run_ffmpeg_reports_tail_on_failure() -> None:
    with pytest.raises(RuntimeError, match=r"ffmpeg test failed \(exit"):
        run_ffmpeg([FFMPEG, "-hide_banner", "-i", "definitely-missing-input.mp4", "-f", "null", "-"], what="ffmpeg test")


def test_clip_last_seconds_modes(synth_video: Path, tmp_path: Path) -> None:
    tail = clip_last_seconds(synth_video, tmp_path / "tail.mp4", seconds=1)
    assert tail.is_file() and tail.stat().st_size > 0
    ranged = clip_last_seconds(synth_video, tmp_path / "range.mp4", seconds=1, start=0.5)
    assert ranged.is_file() and ranged.stat().st_size > 0
    with pytest.raises(FileNotFoundError):
        clip_last_seconds(tmp_path / "nope.mp4", tmp_path / "x.mp4", seconds=1)


def test_apply_brand_with_and_without_logo(synth_video: Path, tmp_path: Path) -> None:
    branded = apply_brand(synth_video, tmp_path / "branded.mp4", {"logo_path": "assets/logo.png", "opacity": 0.8})
    assert branded.is_file() and branded.stat().st_size > 0
    plain = apply_brand(synth_video, tmp_path / "plain.mp4", {"logo_path": "assets/does-not-exist.png"})
    assert plain.is_file() and plain.stat().st_size > 0
    empty = apply_brand(synth_video, tmp_path / "empty.mp4", {"logo_path": ""})
    assert empty.is_file()


def test_compose_brand_sequence_joins_reusable_intro_and_outro(synth_video: Path, tmp_path: Path) -> None:
    intro = clip_last_seconds(synth_video, tmp_path / "intro.mp4", seconds=1)
    outro = clip_last_seconds(synth_video, tmp_path / "outro.mp4", seconds=1, start=0)
    joined = compose_brand_sequence(
        [intro, synth_video, outro], tmp_path / "joined.mp4", width=320, height=180
    )
    assert joined.is_file() and joined.stat().st_size > 0


def test_compose_brand_sequence_accepts_silent_bumpers(synth_video: Path, tmp_path: Path) -> None:
    silent = tmp_path / "silent.mp4"
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30", "-t", "0.5", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(silent)],
        check=True, capture_output=True,
    )
    joined = compose_brand_sequence(
        [silent, synth_video, silent], tmp_path / "joined-silent.mp4", width=320, height=180
    )
    assert joined.is_file() and joined.stat().st_size > 0


def test_make_social_pair(synth_video: Path, tmp_path: Path) -> None:
    h, v = make_social_pair(synth_video, tmp_path, "t", shorts_w=270, shorts_h=480, landscape_w=320, landscape_h=180)
    assert h.name == "clip-horizontal-t.mp4" and v.name == "clip-vertical-t.mp4"
    assert h.stat().st_size > 0 and v.stat().st_size > 0


def test_trim_clip_validation_and_output(synth_video: Path, tmp_path: Path) -> None:
    out = trim_clip(synth_video, tmp_path / "trim.mp4", 0.2, 1.2)
    assert out.is_file() and out.stat().st_size > 0
    with pytest.raises(ValueError):
        trim_clip(synth_video, tmp_path / "bad.mp4", 1.0, 1.0)
    with pytest.raises(ValueError):
        trim_clip(synth_video, tmp_path / "bad.mp4", -1.0, 1.0)
    with pytest.raises(ValueError, match="differ"):
        trim_clip(synth_video, synth_video, 0.0, 1.0)
    with pytest.raises(FileNotFoundError):
        trim_clip(tmp_path / "nope.mp4", tmp_path / "x.mp4", 0.0, 1.0)


def test_music_helpers_and_mix(synth_video: Path, tmp_path: Path) -> None:
    assert music_volume({"music": {"volume": 0.99}}) == pytest.approx(0.35)
    assert music_volume({"music": {"volume": "x"}}) == pytest.approx(0.10)
    assert resolve_music_path({"music": {"path": str(tmp_path / "missing.mp3")}}) is None

    # Disabled / missing bed -> original path back, no ffmpeg call.
    assert maybe_mix_music(synth_video, tmp_path / "off.mp4", {"music": {"enabled": False}}) == synth_video
    assert maybe_mix_music(synth_video, tmp_path / "skip.mp4", {"music": {"enabled": True, "path": str(tmp_path / "none.mp3")}}) == synth_video

    bed = tmp_path / "bed.m4a"
    subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "1", "-c:a", "aac", str(bed)],
        check=True, capture_output=True,
    )
    mixed = maybe_mix_music(synth_video, tmp_path / "mixed.mp4", {"music": {"enabled": True, "path": str(bed), "volume": 0.1}})
    assert mixed == tmp_path / "mixed.mp4" and mixed.stat().st_size > 0


def test_run_pipeline_end_to_end(synth_video: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    out_dir = tmp_path / "out"
    cfg = {
        "buffer_seconds": 30,
        "brand": {"logo_path": "assets/logo.png", "opacity": 0.85, "position": "top_left", "margin_px": 12},
        "captions": {"enabled": True, "engine": "demo"},
        "music": {"enabled": False},
        "output": {"dir": str(out_dir), "shorts_width": 270, "shorts_height": 480, "landscape_width": 320, "landscape_height": 180},
        "review": {"require_approval": True},
    }
    branded = run_pipeline(synth_video, cfg, dry_run=True, start=0.0, duration=1.4)
    assert branded.is_file()
    items = ReviewQueue(out_dir / "review-queue.json").list(status="pending")
    assert len(items) == 1
    item = items[0]
    for attr in ("video_path", "horizontal_path", "vertical_path", "vertical_captioned_path"):
        value = getattr(item, attr)
        assert value, attr
        assert Path(value).is_file() and Path(value).stat().st_size > 0, attr
    assert item.source_path == str(synth_video)


def test_run_pipeline_can_rotate_intro_and_outro_assets(synth_video: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    intro = clip_last_seconds(synth_video, tmp_path / "intro.mp4", seconds=1)
    outro = clip_last_seconds(synth_video, tmp_path / "outro.mp4", seconds=1, start=0)
    out_dir = tmp_path / "sequence-out"
    cfg = {
        "buffer_seconds": 30,
        "brand": {
            "logo_path": "",
            "intro_paths": [str(intro)],
            "outro_paths": [str(outro)],
        },
        "captions": {"enabled": False},
        "music": {"enabled": False},
        "output": {"dir": str(out_dir), "shorts_width": 270, "shorts_height": 480, "landscape_width": 320, "landscape_height": 180},
        "review": {"require_approval": True},
    }
    branded = run_pipeline(synth_video, cfg, dry_run=True, start=0.0, duration=1)
    assert branded.is_file()
    item = ReviewQueue(out_dir / "review-queue.json").list(status="pending")[0]
    assert Path(item.video_path).stat().st_size == branded.stat().st_size


def test_run_pipeline_without_review_gate_writes_dry_run(synth_video: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "0")
    out_dir = tmp_path / "out"
    cfg = {
        "brand": {"logo_path": ""},
        "captions": {"enabled": False},
        "music": {"enabled": False},
        "output": {"dir": str(out_dir), "shorts_width": 270, "shorts_height": 480, "landscape_width": 320, "landscape_height": 180},
        "review": {"require_approval": False},
        "youtube": {"enabled": False},
    }
    run_pipeline(synth_video, cfg, dry_run=True, duration=1)
    assert list(out_dir.glob("upload-dry-run-*.json"))
    assert not (out_dir / "review-queue.json").exists()
