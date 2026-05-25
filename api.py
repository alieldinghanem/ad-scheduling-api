import os
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from main import load_json_from_url, run_scheduler


BACKEND_AI_DATA_URL = os.getenv(
    "BACKEND_AI_DATA_URL",
    "https://nub-adex.runasp.net/api/Scheduling/ai-data",
)

app = FastAPI(title="AD Scheduling API")


@app.get("/")
def root():
    return {"message": "AD Scheduling API is running"}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/test-backend")
def test_backend() -> Dict[str, Any]:
    try:
        start = time.time()
        payload = load_json_from_url(BACKEND_AI_DATA_URL)
        end = time.time()

        return {
            "status": "backend loaded",
            "seconds": round(end - start, 2),
            "keys": list(payload.keys()) if isinstance(payload, dict) else [],
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/schedule")
def generate_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        start = time.time()
        result = run_scheduler(payload)
        end = time.time()

        result["debugTiming"] = {
            "schedulerSeconds": round(end - start, 2)
        }

        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/schedule/from-backend")
def generate_schedule_from_backend() -> Dict[str, Any]:
    try:
        t1 = time.time()
        payload = load_json_from_url(BACKEND_AI_DATA_URL)
        t2 = time.time()

        result = run_scheduler(payload)
        t3 = time.time()

        result["debugTiming"] = {
            "loadBackendSeconds": round(t2 - t1, 2),
            "schedulerSeconds": round(t3 - t2, 2),
            "totalSeconds": round(t3 - t1, 2),
        }

        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
