import json
import multiprocessing as mp
import os
import queue
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from main import load_json_from_url, run_scheduler


BACKEND_AI_DATA_URL = os.getenv(
    "BACKEND_AI_DATA_URL",
    "https://nub-adex.runasp.net/api/Scheduling/ai-data",
)
BACKEND_FETCH_TIMEOUT_SECONDS = int(os.getenv("BACKEND_FETCH_TIMEOUT_SECONDS", "60"))
SCHEDULER_TIMEOUT_SECONDS = int(os.getenv("SCHEDULER_TIMEOUT_SECONDS", "1200"))
SCHEDULER_JOB_WORKERS = int(os.getenv("SCHEDULER_JOB_WORKERS", "1"))
LATEST_SCHEDULE_FILE = Path(os.getenv("LATEST_SCHEDULE_FILE", "latest_schedule.json"))
GENERATION_STATUS_FILE = Path(
    os.getenv("GENERATION_STATUS_FILE", "latest_schedule_status.json")
)
SCHEDULE_OUTPUT_VERSION = "20260617-project-5-7-v4"

app = FastAPI(title="AD Scheduling API")
job_executor = ThreadPoolExecutor(max_workers=max(1, SCHEDULER_JOB_WORKERS))
jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = Lock()


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON safely so readers never see a partially written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _run_scheduler_worker(payload: Dict[str, Any], result_queue) -> None:
    try:
        result_queue.put(("ok", run_scheduler(payload)))
    except Exception as exc:
        result_queue.put(("error", str(exc)))


def _run_scheduler_with_timeout(
    payload: Dict[str, Any],
    timeout_seconds: int,
) -> Dict[str, Any]:
    """Run the scheduler in a child process so a real timeout can terminate it."""
    context = mp.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_run_scheduler_worker,
        args=(payload, result_queue),
    )
    process.start()

    deadline = time.monotonic() + timeout_seconds
    status = None
    value = None

    try:
        while True:
            try:
                status, value = result_queue.get_nowait()
                process.join(5)
                break
            except queue.Empty:
                pass

            if not process.is_alive():
                process.join(5)
                try:
                    status, value = result_queue.get_nowait()
                except queue.Empty as exc:
                    raise RuntimeError(
                        "Scheduler stopped without returning a result."
                    ) from exc
                break

            if time.monotonic() >= deadline:
                process.terminate()
                process.join(5)
                raise TimeoutError(
                    f"Scheduler exceeded {timeout_seconds} seconds. "
                    "Check backend data size, constraints, or scheduler performance."
                )

            time.sleep(0.2)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        result_queue.close()
        result_queue.join_thread()

    if status == "error":
        raise RuntimeError(value)

    if not isinstance(value, dict):
        raise RuntimeError("Scheduler returned an invalid result.")

    return value


def _payload_counts(payload: Dict[str, Any]) -> Dict[str, int]:
    container = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return {
        "regularCourses": len(container.get("regularCourses") or []),
        "arabicCourses": len(container.get("arabicCourses") or []),
        "aptechCourses": len(container.get("aptechCourses") or []),
        "regularInstructors": len(container.get("regularInstructors") or []),
        "arabicInstructors": len(container.get("arabicInstructors") or []),
        "aptechInstructors": len(container.get("aptechInstructors") or []),
        "rooms": len(container.get("rooms") or []),
        "studentGroups": len(container.get("studentGroups") or []),
    }


def _save_latest_schedule(result: Dict[str, Any]) -> None:
    result.setdefault("metadata", {})
    result["metadata"]["apiCodeVersion"] = SCHEDULE_OUTPUT_VERSION
    _write_json_atomic(LATEST_SCHEDULE_FILE, result)


def _save_generation_status(status: Dict[str, Any]) -> None:
    status = {
        "apiCodeVersion": SCHEDULE_OUTPUT_VERSION,
        "updatedAt": round(time.time(), 3),
        **status,
    }
    _write_json_atomic(GENERATION_STATUS_FILE, status)


def _load_generation_status() -> Dict[str, Any]:
    if not GENERATION_STATUS_FILE.exists():
        return {}

    try:
        with GENERATION_STATUS_FILE.open("r", encoding="utf-8") as file:
            status = json.load(file)
    except Exception:
        return {}

    if not isinstance(status, dict):
        return {}

    # Status files are operational state, so ignore state written by another
    # API version. A fresh refresh request can create a new status file.
    if status.get("apiCodeVersion") != SCHEDULE_OUTPUT_VERSION:
        return {}

    return status


def _load_latest_schedule() -> Dict[str, Any]:
    """
    Return the latest valid saved schedule.

    Important: a previously generated schedule remains readable after an API
    deployment. New schedules still receive apiCodeVersion when saved, but the
    endpoint does not reject a usable schedule only because its version tag is
    missing or older.
    """
    if not LATEST_SCHEDULE_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "No schedule has been generated yet. "
                "Open /schedule/from-backend?refresh=true once, then use "
                "/schedule/from-backend."
            ),
        )

    try:
        with LATEST_SCHEDULE_FILE.open("r", encoding="utf-8") as file:
            result = json.load(file)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read saved schedule: {exc}",
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500,
            detail="Saved schedule is not a valid JSON object.",
        )

    return result


def _run_scheduler_job(
    payload: Dict[str, Any],
    fetch_seconds: float,
    job_id: str,
    raw_counts: Dict[str, int],
    created_at: float,
) -> Dict[str, Any]:
    started = time.perf_counter()

    try:
        # Use the same real timeout protection as the direct /schedule endpoint.
        result = _run_scheduler_with_timeout(payload, SCHEDULER_TIMEOUT_SECONDS)
        elapsed = time.perf_counter() - started

        result.setdefault("metadata", {})
        result["metadata"]["apiTimingSeconds"] = {
            "fetchBackend": round(fetch_seconds, 3),
            "schedule": round(elapsed, 3),
            "total": round(fetch_seconds + elapsed, 3),
        }

        # Only replace the latest schedule after a successful generation.
        _save_latest_schedule(result)
        _save_generation_status(
            {
                "jobId": job_id,
                "status": "completed",
                "elapsedSeconds": round(time.time() - created_at, 3),
                "fetchSeconds": round(fetch_seconds, 3),
                "rawCounts": raw_counts,
                "totalSessions": result.get("totalSessions"),
                "message": (
                    "Schedule generation completed. "
                    "Open /schedule/from-backend."
                ),
            }
        )
        return result

    except TimeoutError as exc:
        _save_generation_status(
            {
                "jobId": job_id,
                "status": "failed",
                "failureType": "timeout",
                "elapsedSeconds": round(time.time() - created_at, 3),
                "fetchSeconds": round(fetch_seconds, 3),
                "rawCounts": raw_counts,
                "error": str(exc),
                "message": (
                    "Schedule generation timed out. "
                    "The previous saved schedule is still available at "
                    "/schedule/from-backend."
                ),
            }
        )
        raise

    except Exception as exc:
        _save_generation_status(
            {
                "jobId": job_id,
                "status": "failed",
                "failureType": "scheduler_error",
                "elapsedSeconds": round(time.time() - created_at, 3),
                "fetchSeconds": round(fetch_seconds, 3),
                "rawCounts": raw_counts,
                "error": str(exc),
                "message": (
                    "Schedule generation failed. Check Render logs. "
                    "The previous saved schedule remains available."
                ),
            }
        )
        raise


def _create_job(payload: Dict[str, Any], fetch_seconds: float) -> Dict[str, Any]:
    job_id = uuid4().hex
    created_at = time.time()
    raw_counts = _payload_counts(payload)

    _save_generation_status(
        {
            "jobId": job_id,
            "status": "running",
            "createdAt": round(created_at, 3),
            "elapsedSeconds": 0,
            "fetchSeconds": round(fetch_seconds, 3),
            "rawCounts": raw_counts,
            "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
            "message": (
                "Schedule generation started in the background. "
                "Use /schedule/status to follow its status."
            ),
        }
    )

    future = job_executor.submit(
        _run_scheduler_job,
        payload,
        fetch_seconds,
        job_id,
        raw_counts,
        created_at,
    )

    with jobs_lock:
        jobs[job_id] = {
            "jobId": job_id,
            "status": "running",
            "createdAt": created_at,
            "fetchSeconds": round(fetch_seconds, 3),
            "rawCounts": raw_counts,
            "future": future,
        }

    return {
        "jobId": job_id,
        "status": "running",
        "fetchSeconds": round(fetch_seconds, 3),
        "rawCounts": raw_counts,
        "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
        "message": (
            "Schedule generation started in the background. "
            "Use /schedule/status to follow it, then open "
            "/schedule/from-backend for the generated schedule."
        ),
    }


def _running_job_summary() -> Dict[str, Any]:
    with jobs_lock:
        job_items = list(jobs.items())

    for job_id, job in reversed(job_items):
        future: Future = job["future"]
        if future.done():
            continue

        return {
            "jobId": job_id,
            "status": "running",
            "elapsedSeconds": round(time.time() - job["createdAt"], 3),
            "fetchSeconds": job["fetchSeconds"],
            "rawCounts": job["rawCounts"],
            "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
            "message": (
                "A schedule generation job is running. "
                "Use /schedule/status to follow it."
            ),
        }

    return {}


def _active_generation_status() -> Dict[str, Any]:
    running = _running_job_summary()
    if running:
        return running

    status = _load_generation_status()
    if not status:
        return {}

    # If the persisted file says "running" but there is no in-memory Future,
    # the service was restarted/redeployed while that job was running. That
    # job cannot still be managed by this process, so report it as interrupted
    # instead of pretending it is still running for another 20 minutes.
    if status.get("status") == "running":
        created_at = float(status.get("createdAt") or status.get("updatedAt") or 0)
        elapsed = max(0.0, time.time() - created_at)
        return {
            **status,
            "status": "interrupted",
            "elapsedSeconds": round(elapsed, 3),
            "message": (
                "The previous generation was interrupted by a service restart "
                "or deployment. Open /schedule/from-backend?refresh=true to "
                "start a new generation job."
            ),
        }

    return status


def _start_backend_schedule_job() -> Dict[str, Any]:
    running = _running_job_summary()
    if running:
        return running

    started = time.perf_counter()
    payload = load_json_from_url(
        BACKEND_AI_DATA_URL,
        timeout=BACKEND_FETCH_TIMEOUT_SECONDS,
    )
    fetch_seconds = time.perf_counter() - started
    return _create_job(payload, fetch_seconds)


def _resolve_job(job_id: str) -> Dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        persisted = _load_generation_status()
        if persisted.get("jobId") == job_id:
            return persisted
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    future: Future = job["future"]
    elapsed = round(time.time() - job["createdAt"], 3)

    if not future.done():
        return {
            "jobId": job_id,
            "status": "running",
            "elapsedSeconds": elapsed,
            "fetchSeconds": job["fetchSeconds"],
            "rawCounts": job["rawCounts"],
            "timeoutSeconds": SCHEDULER_TIMEOUT_SECONDS,
        }

    try:
        result = future.result()
    except Exception as exc:
        with jobs_lock:
            job["status"] = "failed"
            job["error"] = str(exc)
        return {
            "jobId": job_id,
            "status": "failed",
            "elapsedSeconds": elapsed,
            "error": str(exc),
        }

    with jobs_lock:
        job["status"] = "completed"
        job["result"] = result

    return {
        "jobId": job_id,
        "status": "completed",
        "elapsedSeconds": elapsed,
        "result": result,
    }


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "message": "AD Scheduling API is running",
        "apiCodeVersion": SCHEDULE_OUTPUT_VERSION,
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/schedule/status")
def schedule_status() -> Dict[str, Any]:
    status = _active_generation_status()
    if status:
        return status

    return {
        "status": "idle",
        "message": "No schedule generation job is currently running.",
    }


@app.get("/schedule/jobs/{job_id}")
def get_schedule_job(job_id: str) -> Dict[str, Any]:
    return _resolve_job(job_id)


@app.get("/schedule/latest")
def latest_schedule() -> Dict[str, Any]:
    return _load_latest_schedule()


@app.post("/schedule")
def generate_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        result = _run_scheduler_with_timeout(payload, SCHEDULER_TIMEOUT_SECONDS)
        result.setdefault("metadata", {})
        result["metadata"]["apiTimingSeconds"] = {
            "schedule": round(time.perf_counter() - started, 3),
        }
        _save_latest_schedule(result)
        return result
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/schedule/from-backend")
def generate_schedule_from_backend(refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        try:
            return _start_backend_schedule_job()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    # The normal endpoint always serves the last successfully saved schedule.
    # Generation status is available separately at /schedule/status.
    return _load_latest_schedule()
