import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from main import load_json_from_url, run_scheduler


BACKEND_AI_DATA_URL = os.getenv(
    "BACKEND_AI_DATA_URL",
    "https://nub-adex.runasp.net/api/Scheduling/ai-data",
)

app = FastAPI(title="AD Scheduling API")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/schedule")
def generate_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return run_scheduler(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/schedule/from-backend")
def generate_schedule_from_backend() -> Dict[str, Any]:
    try:
        payload = load_json_from_url(BACKEND_AI_DATA_URL)
        return run_scheduler(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
