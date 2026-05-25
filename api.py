import multiprocessing as mp
import os
import queue
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from main import load_json_from_url, normalize_payload, run_scheduler


BACKEND_AI_DATA_URL = os.getenv(
    "BACKEND_AI_DATA_URL",
    "https://nub-adex.runasp.net/api/Scheduling/ai-data",
)
BACKEND_FETCH_TIMEOUT_SECONDS = int(os.getenv("BACKEND_FETCH_TIMEOUT_SECONDS", "60"))
SCHEDULER_TIMEOUT_SECONDS = int(os.getenv("SCHEDULER_TIMEOUT_SECONDS", "240"))

app = FastAPI(title="AD Scheduling API")


def _run_scheduler_worker(payload: Dict[str, Any], result_queue) -> None:
    try:
        result_queue.put(("ok", run_scheduler(payload)))
    except Exception as exc:
        result_queue.put(("error", str(exc)))


def _run_scheduler_with_timeout(payload: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
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
                raise RuntimeError("Scheduler stopped without returning a result.") from exc
            break

        if time.monotonic() >= deadline:
            process.terminate()
            process.join(5)
            raise TimeoutError(
                f"Scheduler exceeded {timeout_seconds} seconds. "
                "Check backend data size or run the scheduler as a background job."
            )

        time.sleep(0.2)

    if status == "error":
        raise RuntimeError(value)

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


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "AD Scheduling API is running"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/schedule")
def generate_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        result = _run_scheduler_with_timeout(payload, SCHEDULER_TIMEOUT_SECONDS)
        result.setdefault("metadata", {})
        result["metadata"]["apiTimingSeconds"] = {
            "schedule": round(time.perf_counter() - started, 3),
        }
        return result
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/schedule/from-backend/debug")
def debug_backend_payload() -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = load_json_from_url(
            BACKEND_AI_DATA_URL,
            timeout=BACKEND_FETCH_TIMEOUT_SECONDS,
        )
        normalized = normalize_payload(payload)
        return {
            "status": "ok",
            "backendUrl": BACKEND_AI_DATA_URL,
            "fetchSeconds": round(time.perf_counter() - started, 3),
            "rawCounts": _payload_counts(payload),
            "normalizedCounts": _payload_counts(normalized),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/schedule/from-backend")
def generate_schedule_from_backend() -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = load_json_from_url(
            BACKEND_AI_DATA_URL,
            timeout=BACKEND_FETCH_TIMEOUT_SECONDS,
        )
        fetched_at = time.perf_counter()
        result = _run_scheduler_with_timeout(payload, SCHEDULER_TIMEOUT_SECONDS)
        result.setdefault("metadata", {})
        result["metadata"]["apiTimingSeconds"] = {
            "fetchBackend": round(fetched_at - started, 3),
            "schedule": round(time.perf_counter() - fetched_at, 3),
            "total": round(time.perf_counter() - started, 3),
        }
        return result
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
