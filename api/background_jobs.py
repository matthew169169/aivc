"""Bounded background execution with atomic, restart-aware job records.

One process owns the queue. Status/log files survive process restarts on the
cloud data volume; interrupted work is marked failed instead of silently lost.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable


class JobQueueError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def result_status(result: dict[str, Any], fallback: str = "completed") -> str:
    value = str(result.get("result_status") or result.get("status") or "").lower()
    if value in {"failed", "error", "input_missing", "parse_failed", "missing_model"} or value.endswith("_failed"):
        return "failed"
    if value.startswith("skipped") or value == "dry_run":
        return "skipped"
    return fallback


def new_record(job_type: str, run_id: str, root: Path) -> dict[str, Any]:
    job_id = f"{job_type}_{uuid.uuid4().hex[:12]}"
    now = time.time()
    return {"job_id": job_id, "job_type": job_type, "run_id": run_id,
            "status": "queued", "created_at": now, "updated_at": now,
            "log_path": str(root / f"{job_id}.log")}


def execute_job(record: dict[str, Any], callback: Callable[[Path], dict[str, Any]], *, final_status: str = "completed") -> dict[str, Any]:
    log_path = Path(record["log_path"])
    path = log_path.with_suffix(".json")
    started = time.time()
    record = {**record, "status": "running", "started_at": started, "updated_at": started}
    atomic_json(path, record)
    try:
        result = callback(log_path)
        record.update(status=result_status(result, final_status), result=result)
    except Exception as exc:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"ERROR: {type(exc).__name__}: {exc}\n")
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    record.update(updated_at=time.time(), elapsed_seconds=round(time.time() - started, 6))
    atomic_json(path, record)
    return record


def run_inline(job_type: str, run_id: str, root: Path, callback: Callable[[Path], dict[str, Any]], *, final_status: str = "completed") -> dict[str, Any]:
    record = new_record(job_type, run_id, root)
    root.mkdir(parents=True, exist_ok=True)
    Path(record["log_path"]).write_text("", encoding="utf-8")
    return execute_job(record, callback, final_status=final_status)


class JobQueue:
    def __init__(self, *, workers: int = 1, capacity: int = 8):
        self.workers = max(1, workers)
        self.capacity = max(self.workers, capacity)
        self._lock = threading.RLock()
        self._executor: ThreadPoolExecutor | None = None
        self._active: dict[tuple[str, str], str] = {}

    def has_active(self, root: Path, run_id: str | None = None) -> bool:
        with self._lock:
            return any(key[0] == str(root.resolve()) and (run_id is None or key[1] == run_id) for key in self._active)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"workers": self.workers, "capacity": self.capacity, "active_jobs": len(self._active)}

    def submit(self, job_type: str, run_id: str, root: Path, callback: Callable[[Path], dict[str, Any]], *, final_status: str = "completed") -> dict[str, Any]:
        root = root.resolve()
        key = (str(root), run_id)
        with self._lock:
            if key in self._active:
                raise JobQueueError(409, f"A job is already active for {run_id}: {self._active[key]}. Check Jobs before submitting again.")
            if len(self._active) >= self.capacity:
                raise JobQueueError(429, "The analysis queue is full. Wait for an existing job to finish.")
            root.mkdir(parents=True, exist_ok=True)
            record = new_record(job_type, run_id, root)
            Path(record["log_path"]).write_text("Queued for background execution.\n", encoding="utf-8")
            atomic_json(root / f'{record["job_id"]}.json', record)
            self._active[key] = record["job_id"]
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="omics-job")
            try:
                self._executor.submit(self._execute, key, record, callback, final_status)
            except Exception:
                self._active.pop(key, None)
                record.update(status="failed", error="Background worker could not be started.", updated_at=time.time())
                atomic_json(root / f'{record["job_id"]}.json', record)
                raise
            return dict(record)

    def _execute(self, key, record, callback, final_status):
        try:
            execute_job(record, callback, final_status=final_status)
        finally:
            with self._lock:
                self._active.pop(key, None)

    def shutdown(self) -> None:
        with self._lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=True)


def recover_interrupted_jobs(root: Path) -> int:
    """Call once on process startup, before accepting any new submissions."""
    count = 0
    for path in root.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("status") not in {"queued", "running"}:
            continue
        record.update(status="failed", updated_at=time.time(),
                      error="Server restarted before this job finished. Review its outputs and submit it again.",
                      interruption_reason="server_restart")
        atomic_json(path, record)
        log = root / f'{path.stem}.log'
        with log.open("a", encoding="utf-8") as handle:
            handle.write("ERROR: Server restarted before this job finished.\n")
        count += 1
    return count
