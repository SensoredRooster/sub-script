import tempfile
from pathlib import Path

import pytest

from subscript.production_bridge import CONTRACT, CONTRACT_VERSION, BridgeRun, validate_production_job


def test_validate_production_job_normalizes_fields():
    job = validate_production_job({
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "job_id": "abc",
        "origin": "universal-ai-studio",
        "intent": "clip",
        "source": {"path": "C:/video.mp4"},
        "edit": {"start_seconds": 12.5, "duration_seconds": 30},
        "delivery": {"review_required": True, "formats": ["9:16"]},
    })
    assert job["job_id"] == "abc"
    assert job["edit"]["start_seconds"] == 12.5
    assert job["delivery"]["review_required"] is True


def test_validate_rejects_wrong_contract():
    with pytest.raises(ValueError):
        validate_production_job({"contract": "wrong", "version": "1.0", "source": {"path": "x.mp4"}})


def test_validate_rejects_unsafe_job_id():
    with pytest.raises(ValueError):
        validate_production_job({
            "contract": CONTRACT,
            "version": CONTRACT_VERSION,
            "job_id": "../escape",
            "source": {"path": "x.mp4"},
        })


def test_bridge_run_persists_compatible_state():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        job = validate_production_job({
            "contract": CONTRACT,
            "version": CONTRACT_VERSION,
            "job_id": "bridge-test",
            "source": {"path": "x.mp4"},
        })
        run = BridgeRun.create(out, job)
        run.stage("validate", "running")
        run.stage("validate", "complete")
        run.artifact("demo", {"ok": True})
        state = run.snapshot()
        assert state["pipeline_id"] == "subscript-clip"
        assert state["stages"]["validate"]["status"] == "complete"
        assert state["artifacts"]["demo"]["value"]["ok"] is True
