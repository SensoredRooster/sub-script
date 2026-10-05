"""Universal production-job bridge for local integrations such as Universal AI Studio."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any

from subscript.pipeline import run_pipeline
from subscript.telemetry import log_event


CONTRACT = "open-production-job"
CONTRACT_VERSION = "1.0"
_ALLOWED_INTENTS = {"clip", "highlight", "edit", "repurpose"}
_BRIDGE_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_production_job(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Production job must be a JSON object.")
    if payload.get("contract") != CONTRACT:
        raise ValueError(f"contract must be {CONTRACT!r}.")
    if str(payload.get("version") or "") != CONTRACT_VERSION:
        raise ValueError(f"version must be {CONTRACT_VERSION!r}.")

    job_id = str(payload.get("job_id") or uuid.uuid4())
    source = payload.get("source") or {}
    source_path = str(source.get("path") or "").strip()
    if not source_path:
        raise ValueError("source.path is required for a local SubScript bridge job.")

    intent = str(payload.get("intent") or "clip").strip().lower()
    if intent not in _ALLOWED_INTENTS:
        raise ValueError(f"Unsupported intent: {intent}")

    edit = payload.get("edit") or {}
    start = edit.get("start_seconds")
    duration = edit.get("duration_seconds")
    if start is not None:
        start = float(start)
        if start < 0:
            raise ValueError("edit.start_seconds must be >= 0.")
    if duration is not None:
        duration = float(duration)
        if duration <= 0:
            raise ValueError("edit.duration_seconds must be > 0.")

    return {
        "contract": CONTRACT,
        "version": CONTRACT_VERSION,
        "job_id": job_id,
        "origin": str(payload.get("origin") or "external"),
        "intent": intent,
        "source": {"path": source_path, "kind": str(source.get("kind") or "video")},
        "edit": {
            "start_seconds": start,
            "duration_seconds": duration,
            "auto_highlight": bool(edit.get("auto_highlight", False)),
        },
        "delivery": {
            "review_required": bool((payload.get("delivery") or {}).get("review_required", True)),
            "formats": list((payload.get("delivery") or {}).get("formats") or ["16:9", "9:16"]),
        },
        "metadata": dict(payload.get("metadata") or {}),
    }


class BridgeRun:
    def __init__(self, root: Path, job: dict[str, Any]):
        self.root = root
        self.job = job
        self.state_path = root / "run.json"
        self.events_path = root / "events.jsonl"

    @classmethod
    def create(cls, out_dir: Path, job: dict[str, Any]) -> "BridgeRun":
        root = out_dir / "bridge-runs" / str(job["job_id"])
        root.mkdir(parents=True, exist_ok=True)
        run = cls(root, job)
        if not run.state_path.exists():
            run._write({
                "run_id": job["job_id"],
                "pipeline_id": "subscript-clip",
                "status": "created",
                "current_stage": None,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "request": job.get("metadata", {}).get("request"),
                "metadata": {
                    "origin": job["origin"],
                    "contract": job["contract"],
                    "contract_version": job["version"],
                },
                "stages": {},
                "artifacts": {"production_job": {"value": job}},
                "last_error": None,
                "resumable": False,
            })
            run.emit("run_created", pipeline_id="subscript-clip")
        return run

    @classmethod
    def open(cls, out_dir: Path, run_id: str) -> "BridgeRun":
        root = out_dir / "bridge-runs" / run_id
        state_path = root / "run.json"
        if not state_path.is_file():
            raise FileNotFoundError(f"Unknown bridge run: {run_id}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        job = ((state.get("artifacts") or {}).get("production_job") or {}).get("value") or {}
        return cls(root, job)

    def _write(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _utc_now()
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        temp.replace(self.state_path)

    def state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def emit(self, event: str, **fields: Any) -> None:
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": _utc_now(), "event": event, "run_id": self.job.get("job_id"), **fields}, default=str) + "\n")

    def stage(self, name: str, status: str, **details: Any) -> None:
        state = self.state()
        record = state["stages"].setdefault(name, {})
        record.update({"status": status, **details})
        if status == "running":
            record["started_at"] = _utc_now()
            state["status"] = "running"
            state["current_stage"] = name
        elif status == "complete":
            record["completed_at"] = _utc_now()
            state["current_stage"] = None
        elif status == "failed":
            record["failed_at"] = _utc_now()
            state["status"] = "failed"
            state["current_stage"] = name
            state["last_error"] = str(details.get("error") or "Bridge stage failed")
        self._write(state)
        self.emit(f"stage_{status}", stage=name, **details)

    def artifact(self, name: str, value: Any) -> None:
        state = self.state()
        state["artifacts"][name] = {"value": value, "updated_at": _utc_now()}
        self._write(state)
        self.emit("artifact_saved", artifact=name)

    def complete(self) -> None:
        state = self.state()
        state["status"] = "complete"
        state["current_stage"] = None
        state["last_error"] = None
        state["completed_at"] = _utc_now()
        self._write(state)
        self.emit("run_completed")

    def snapshot(self) -> dict[str, Any]:
        state = self.state()
        events = []
        if self.events_path.is_file():
            for line in self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        state["events"] = events
        return state


def execute_bridge_job(job: dict[str, Any], cfg: dict[str, Any], out_dir: Path) -> None:
    run = BridgeRun.create(out_dir, job)
    source = Path(job["source"]["path"]).expanduser()
    try:
        run.stage("validate", "running")
        if not source.is_file():
            raise FileNotFoundError(f"Source video not found: {source}")
        run.stage("validate", "complete", source=str(source.resolve()))

        run.stage("render", "running")
        pipeline_cfg = deepcopy(cfg)
        pipeline_cfg.setdefault("review", {})["require_approval"] = bool(job["delivery"]["review_required"])
        edit = job["edit"]
        result = run_pipeline(
            source.resolve(),
            pipeline_cfg,
            dry_run=bool(job["delivery"]["review_required"]),
            start=edit.get("start_seconds"),
            duration=edit.get("duration_seconds"),
        )
        run.artifact("master_output", {"path": str(result)})
        run.stage("render", "complete", output=str(result))

        run.stage("review", "running")
        run.artifact("review", {
            "required": bool(job["delivery"]["review_required"]),
            "workspace_url": "/clip#review",
        })
        run.stage("review", "complete", required=bool(job["delivery"]["review_required"]))
        run.complete()
        log_event("production_bridge_complete", "External production job completed", run_id=job["job_id"], origin=job["origin"])
    except Exception as exc:
        state = run.state()
        stage = state.get("current_stage") or "bridge"
        run.stage(stage, "failed", error=str(exc))
        log_event("production_bridge_failed", "External production job failed", level=40, run_id=job["job_id"], error=str(exc))


def submit_bridge_job(payload: dict[str, Any], cfg: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    job = validate_production_job(payload)
    source = Path(job["source"]["path"]).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Source video not found: {source}")
    run = BridgeRun.create(out_dir, job)
    thread = threading.Thread(
        target=_execute_serialized,
        args=(job, cfg, out_dir),
        name=f"subscript-bridge-{job['job_id'][:8]}",
        daemon=True,
    )
    thread.start()
    return run.snapshot()


def _execute_serialized(job: dict[str, Any], cfg: dict[str, Any], out_dir: Path) -> None:
    with _BRIDGE_LOCK:
        execute_bridge_job(job, cfg, out_dir)
