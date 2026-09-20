"""Automatic delivery tests without network or video encoding."""
import json
from pathlib import Path
import pytest
from subscript.pipeline import run_pipeline
from subscript.queue import ReviewQueue
from subscript.publish import PublishResult


@pytest.mark.parametrize("outcome,status", [("uploaded", "uploaded"), ("manual", "approved"), ("error", "pending")])
def test_automatic_delivery(tmp_path, monkeypatch, outcome, status):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    def copy(src, dest, *args, **kwargs):
        Path(dest).write_bytes(b"video")
    monkeypatch.setattr("subscript.pipeline.clip_last_seconds", copy)
    monkeypatch.setattr("subscript.pipeline.apply_brand", copy)
    monkeypatch.setattr("subscript.pipeline.make_social_pair", lambda *a, **kw: (source, source))
    monkeypatch.setattr("subscript.pipeline.maybe_mix_social_pair", lambda h, v, *a: (h, v))
    monkeypatch.setattr("subscript.pipeline.maybe_caption_vertical", lambda *a, **kw: None)
    monkeypatch.setattr("subscript.publish.run_enabled_publishers", lambda *a: [PublishResult(platform="Test", ok=outcome != "error", status=outcome)])
    cfg = {"output": {"dir": str(tmp_path)}, "review": {"require_approval": False}}
    if outcome == "error":
        with pytest.raises(RuntimeError, match="needs attention"):
            run_pipeline(source, cfg, dry_run=False)
    else:
        run_pipeline(source, cfg, dry_run=False)
    items = ReviewQueue(tmp_path / "review-queue.json").list(status=status)
    assert len(items) == 1
    report = tmp_path / "approved" / items[0].id / "publishing-results.json"
    assert json.loads(report.read_text())[0]["status"] == outcome


@pytest.mark.parametrize("required", [True, False])
def test_live_hotkey_obeys_publishing_mode(monkeypatch, tmp_path, required):
    from subscript.live_ui import make_fire_live
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    calls = []
    monkeypatch.setattr("subscript.live_ui.resolve_live_source", lambda cfg: source)
    monkeypatch.setattr("subscript.live_ui.run_pipeline", lambda *a, **kw: calls.append((a, kw)))
    cfg = {"review": {"require_approval": required}, "auto_enqueue": True}
    make_fire_live(cfg)()
    assert calls[0][1]["dry_run"] is required
    assert calls[0][0][1]["review"]["require_approval"] is required


def test_automatic_delivery_respects_environment_override(tmp_path, monkeypatch):
    from subscript.config import apply_env_overrides
    monkeypatch.setenv("SUB_SCRIPT_DRY_RUN", "1")
    cfg = apply_env_overrides({"youtube": {"enabled": True}, "platforms": {"youtube": {"enabled": True}}})
    assert not cfg["youtube"]["enabled"]
    assert not cfg["platforms"]["youtube"]["enabled"]
