import hashlib
import json
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from main import load_json_from_url, run_scheduler

BACKEND_AI_DATA_URL = os.getenv("BACKEND_AI_DATA_URL", "").strip()
BACKEND_FETCH_TIMEOUT_SECONDS = int(os.getenv("BACKEND_FETCH_TIMEOUT_SECONDS", "60"))
SCHEDULER_TIMEOUT_SECONDS = int(os.getenv("SCHEDULER_TIMEOUT_SECONDS", "1200"))
SCHEDULER_JOB_WORKERS = int(os.getenv("SCHEDULER_JOB_WORKERS", "1"))
DATA_DIR = Path(os.getenv("SCHEDULER_DATA_DIR", "."))
LATEST_SCHEDULE_FILE = Path(os.getenv("LATEST_SCHEDULE_FILE", str(DATA_DIR / "latest_schedule.json")))
GENERATION_STATUS_FILE = Path(os.getenv("GENERATION_STATUS_FILE", str(DATA_DIR / "latest_schedule_status.json")))
LATEST_INPUT_FILE = Path(os.getenv("LATEST_INPUT_FILE", str(DATA_DIR / "latest_input.json")))
SCHEDULE_OUTPUT_VERSION = "20260910-render-low-memory-v3"

app = FastAPI(title="AD Scheduling API")
job_executor = ThreadPoolExecutor(max_workers=max(1, SCHEDULER_JOB_WORKERS))
jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = Lock()


def _payload_container(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _payload_semester_id(payload: Dict[str, Any]) -> Any:
    container = _payload_container(payload)
    return container.get("semesterId", payload.get("semesterId"))


def _payload_counts(payload: Dict[str, Any]) -> Dict[str, int]:
    c = _payload_container(payload)
    return {
        "regularCourses": len(c.get("regularCourses") or []),
        "arabicCourses": len(c.get("arabicCourses") or []),
        "aptechCourses": len(c.get("aptechCourses") or []),
        "regularInstructors": len(c.get("regularInstructors") or []),
        "arabicInstructors": len(c.get("arabicInstructors") or []),
        "aptechInstructors": len(c.get("aptechInstructors") or []),
        "rooms": len(c.get("rooms") or []),
        "studentGroups": len(c.get("studentGroups") or []),
    }


def _payload_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _same_semester(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return str(left).strip() == str(right).strip()


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    temp.replace(path)


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"Invalid JSON object in {path.name}")
    return value


def _save_generation_status(status: Dict[str, Any]) -> None:
    _write_json_atomic(
        GENERATION_STATUS_FILE,
        {"apiCodeVersion": SCHEDULE_OUTPUT_VERSION, "updatedAt": round(time.time(), 3), **status},
    )


def _load_generation_status() -> Dict[str, Any]:
    if not GENERATION_STATUS_FILE.exists():
        return {}
    try:
        status = _read_json(GENERATION_STATUS_FILE)
    except Exception:
        return {}
    if status.get("apiCodeVersion") != SCHEDULE_OUTPUT_VERSION:
        return {}
    return status


def _save_latest_input(payload: Dict[str, Any], source_hash: str, fetched_at: float) -> None:
    _write_json_atomic(
        LATEST_INPUT_FILE,
        {
            "source": {
                "backendUrl": BACKEND_AI_DATA_URL,
                "fetchedAt": round(fetched_at, 3),
                "semesterId": _payload_semester_id(payload),
                "dataHash": source_hash,
                "rawCounts": _payload_counts(payload),
            },
            "payload": payload,
        },
    )


def _load_latest_input() -> Dict[str, Any]:
    if not LATEST_INPUT_FILE.exists():
        raise HTTPException(status_code=404, detail="No backend input snapshot has been fetched yet. Use refresh=true first.")
    try:
        return _read_json(LATEST_INPUT_FILE)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read latest backend input snapshot: {exc}") from exc


def _save_latest_schedule(result: Dict[str, Any], source_semester_id: Any, source_hash: str, fetched_at: float) -> None:
    result.setdefault("metadata", {})
    result["metadata"].update(
        {
            "apiCodeVersion": SCHEDULE_OUTPUT_VERSION,
            "sourceSemesterId": source_semester_id,
            "sourceDataHash": source_hash,
            "sourceFetchedAt": round(fetched_at, 3),
        }
    )
    _write_json_atomic(LATEST_SCHEDULE_FILE, result)


def _load_latest_schedule() -> Dict[str, Any]:
    if not LATEST_SCHEDULE_FILE.exists():
        raise HTTPException(status_code=404, detail="No verified schedule has been generated yet. Use /schedule/from-backend?refresh=true.")
    try:
        result = _read_json(LATEST_SCHEDULE_FILE)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read saved schedule: {exc}") from exc

    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    if metadata.get("apiCodeVersion") != SCHEDULE_OUTPUT_VERSION:
        raise HTTPException(status_code=409, detail="The saved schedule is stale for this API version. Generate a fresh schedule with refresh=true.")
    if not metadata.get("sourceDataHash") or "sourceSemesterId" not in metadata:
        raise HTTPException(status_code=409, detail="The saved schedule is legacy/stale and is intentionally blocked.")
    if not _same_semester(metadata.get("semesterId"), metadata.get("sourceSemesterId")):
        raise HTTPException(status_code=409, detail="Saved schedule semester mismatch. Generate a fresh schedule.")
    return result


def _run_scheduler_job(
    payload: Dict[str, Any],
    fetch_seconds: float,
    job_id: str,
    created_at: float,
    source_semester_id: Any,
    source_hash: str,
    source_fetched_at: float,
    raw_counts: Dict[str, int],
) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        # Deliberately run inside the single background thread instead of
        # spawning a second Python interpreter. This keeps memory usage low on
        # constrained Render instances and prevents jobs disappearing when the
        # child process is OOM-killed.
        result = run_scheduler(payload)
        schedule_seconds = time.perf_counter() - started

        if not isinstance(result, dict):
            raise RuntimeError("Scheduler returned an invalid result.")

        result.setdefault("metadata", {})
        output_semester_id = result["metadata"].get("semesterId")
        if not _same_semester(output_semester_id, source_semester_id):
            raise RuntimeError(
                f"Scheduler output semester mismatch: source={source_semester_id}, output={output_semester_id}."
            )

        result["metadata"]["apiTimingSeconds"] = {
            "fetchBackend": round(fetch_seconds, 3),
            "schedule": round(schedule_seconds, 3),
            "total": round(fetch_seconds + schedule_seconds, 3),
        }

        _save_latest_schedule(result, source_semester_id, source_hash, source_fetched_at)
        _save_generation_status(
            {
                "jobId": job_id,
                "status": "completed",
                "createdAt": round(created_at, 3),
                "elapsedSeconds": round(time.time() - created_at, 3),
                "fetchSeconds": round(fetch_seconds, 3),
                "rawCounts": raw_counts,
                "sourceSemesterId": source_semester_id,
                "sourceDataHash": source_hash,
                "totalSessions": result.get("totalSessions"),
                "success": result.get("success"),
                "message": "Schedule generation completed. Open /schedule/from-backend.",
            }
        )
        return result
    except Exception as exc:
        _save_generation_status(
            {
                "jobId": job_id,
                "status": "failed",
                "createdAt": round(created_at, 3),
                "elapsedSeconds": round(time.time() - created_at, 3),
                "fetchSeconds": round(fetch_seconds, 3),
                "rawCounts": raw_counts,
                "sourceSemesterId": source_semester_id,
                "sourceDataHash": source_hash,
                "error": str(exc),
                "message": "Schedule generation failed. Check Render logs.",
            }
        )
        raise


def _create_job(payload: Dict[str, Any], fetch_seconds: float) -> Dict[str, Any]:
    job_id = uuid4().hex
    created_at = time.time()
    source_semester_id = _payload_semester_id(payload)
    source_hash = _payload_hash(payload)
    source_fetched_at = time.time()
    raw_counts = _payload_counts(payload)

    _save_latest_input(payload, source_hash, source_fetched_at)
    _save_generation_status(
        {
            "jobId": job_id,
            "status": "running",
            "createdAt": round(created_at, 3),
            "elapsedSeconds": 0,
            "fetchSeconds": round(fetch_seconds, 3),
            "rawCounts": raw_counts,
            "sourceSemesterId": source_semester_id,
            "sourceDataHash": source_hash,
            "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
            "message": "Schedule generation started in the background. Use /schedule/status to follow it.",
        }
    )

    future = job_executor.submit(
        _run_scheduler_job,
        payload,
        fetch_seconds,
        job_id,
        created_at,
        source_semester_id,
        source_hash,
        source_fetched_at,
        raw_counts,
    )

    with jobs_lock:
        jobs[job_id] = {
            "future": future,
            "createdAt": created_at,
            "fetchSeconds": round(fetch_seconds, 3),
            "rawCounts": raw_counts,
            "sourceSemesterId": source_semester_id,
            "sourceDataHash": source_hash,
        }

    return {
        "jobId": job_id,
        "status": "running",
        "fetchSeconds": round(fetch_seconds, 3),
        "rawCounts": raw_counts,
        "sourceSemesterId": source_semester_id,
        "sourceDataHash": source_hash,
        "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
        "message": "Schedule generation started in the background. Use /schedule/status to follow it.",
    }


def _running_job_summary() -> Dict[str, Any]:
    with jobs_lock:
        items = list(jobs.items())
    for job_id, job in reversed(items):
        future: Future = job["future"]
        if future.done():
            continue
        return {
            "jobId": job_id,
            "status": "running",
            "elapsedSeconds": round(time.time() - job["createdAt"], 3),
            "fetchSeconds": job["fetchSeconds"],
            "rawCounts": job["rawCounts"],
            "sourceSemesterId": job["sourceSemesterId"],
            "sourceDataHash": job["sourceDataHash"],
            "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
            "message": "A schedule generation job is running. Use /schedule/status to follow it.",
        }
    return {}


def _active_generation_status() -> Dict[str, Any]:
    running = _running_job_summary()
    if running:
        return running

    status = _load_generation_status()
    if not status:
        return {}

    if status.get("status") == "running":
        created_at = float(status.get("createdAt") or status.get("updatedAt") or 0)
        return {
            **status,
            "status": "interrupted",
            "elapsedSeconds": round(max(0.0, time.time() - created_at), 3),
            "message": "The previous generation was interrupted by a service restart. Start a new generation with refresh=true.",
        }
    return status


def _start_backend_schedule_job() -> Dict[str, Any]:
    if not BACKEND_AI_DATA_URL:
        raise HTTPException(status_code=503, detail="Backend source not configured. Set BACKEND_AI_DATA_URL to an authorized data endpoint.")
    running = _running_job_summary()
    if running:
        return running
    started = time.perf_counter()
    payload = load_json_from_url(BACKEND_AI_DATA_URL, timeout=BACKEND_FETCH_TIMEOUT_SECONDS, no_cache=True)
    fetch_seconds = time.perf_counter() - started
    return _create_job(payload, fetch_seconds)


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "AD Scheduling API is running", "apiCodeVersion": SCHEDULE_OUTPUT_VERSION}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/schedule/status")
def schedule_status() -> Dict[str, Any]:
    return _active_generation_status() or {"status": "idle", "message": "No schedule generation job is currently running."}


@app.get("/schedule/input/latest")
def latest_backend_input() -> Dict[str, Any]:
    return _load_latest_input()


@app.get("/schedule/latest")
def latest_schedule() -> Dict[str, Any]:
    return _load_latest_schedule()


@app.get("/schedule/jobs/{job_id}")
def get_schedule_job(job_id: str) -> Dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
    if job:
        future: Future = job["future"]
        if not future.done():
            return {
                "jobId": job_id,
                "status": "running",
                "elapsedSeconds": round(time.time() - job["createdAt"], 3),
                "sourceSemesterId": job["sourceSemesterId"],
                "sourceDataHash": job["sourceDataHash"],
            }
        try:
            result = future.result()
            return {"jobId": job_id, "status": "completed", "result": result}
        except Exception as exc:
            return {"jobId": job_id, "status": "failed", "error": str(exc)}

    status = _load_generation_status()
    if status.get("jobId") == job_id:
        return status
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@app.post("/schedule")
def generate_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        result = run_scheduler(payload)
        source_semester_id = _payload_semester_id(payload)
        source_hash = _payload_hash(payload)
        fetched_at = time.time()
        result.setdefault("metadata", {})
        if not _same_semester(result["metadata"].get("semesterId"), source_semester_id):
            raise RuntimeError("Scheduler output semester mismatch.")
        _save_latest_input(payload, source_hash, fetched_at)
        _save_latest_schedule(result, source_semester_id, source_hash, fetched_at)
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/schedule/from-backend")
def generate_schedule_from_backend(refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        try:
            return _start_backend_schedule_job()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    running = _running_job_summary()
    if running:
        return JSONResponse(status_code=202, content=running)
    return _load_latest_schedule()
