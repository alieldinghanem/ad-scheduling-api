# ADEX — Smart Academic Scheduling API

A FastAPI backend for an academic scheduling system that generates conflict-aware timetables from structured university scheduling data.

## Project

ADEX was developed as a graduation project and received a **Grade A**. The system exposes the scheduling engine through a Python/FastAPI API.

The project was designed to handle a university-scale scheduling scenario involving **2,000+ students, 32+ courses, instructors, rooms, student groups, lectures, sections, and laboratory requirements**.

> **Privacy note:** Real university/student/instructor data is not included in this public repository. The repository contains code, tests, and synthetic/minimal sample input only.

## What the system solves

- Instructor availability and double-booking
- Room availability and double-booking
- Student-group conflicts
- Course/session conflicts
- Room type and laboratory requirements
- Room capacity and section capacity
- Online-course scheduling rules
- Arabic and APTECH-specific scheduling rules
- Semester/source-data consistency

The API also supports background schedule-generation jobs and exposes status/latest-result endpoints for long-running scheduling operations.

## Architecture

```text
Client / Frontend
       |
       v
FastAPI (api.py)
       |
       v
Input normalization (main.py)
       |
       v
SchedulingEngine (scheduler.py)
       |
       +---- Constraint-aware scheduling
       +---- Instructor / room / group checks
       +---- Session allocation
       |
       v
Generated schedule + metadata
```

## Repository structure

```text
.
├── api.py
├── main.py
├── scheduler.py
├── scheduler_performance.py
├── aptech_ara.py
├── sitecustomize.py
├── requirements.txt
├── .env.example
├── sample_data/
│   └── sample_input.json
├── tests/
│   └── test_smoke.py
└── .github/
    └── workflows/
```

## Requirements

- Python 3.12
- FastAPI
- Uvicorn

```bash
pip install -r requirements.txt
```

## Run locally

```bash
uvicorn api:app --reload
```

API: `http://127.0.0.1:8000`

Interactive docs: `http://127.0.0.1:8000/docs`

## Run the scheduler directly

```bash
python main.py sample_data/sample_input.json output_schedule.json
```

The sample is synthetic/minimal and contains no real university records.

## API endpoints

### Health
```http
GET /health
```

### Generate from JSON
```http
POST /schedule
Content-Type: application/json
```

Example request:
```json
{
  "semesterId": 1,
  "days": [
    "Saturday"
  ],
  "regularTimeSlots": [
    "09:00-11:00"
  ],
  "targetGroupSize": 150,
  "sectionCapacity": 50,
  "regularCourses": [],
  "arabicCourses": [],
  "aptechCourses": [],
  "regularInstructors": [],
  "arabicInstructors": [],
  "aptechInstructors": [],
  "rooms": [],
  "studentGroups": []
}
```

### Generate from configured backend
```http
GET /schedule/from-backend?refresh=true
```

### Generation status
```http
GET /schedule/status
```

### Latest verified schedule
```http
GET /schedule/latest
```

### Latest backend input snapshot
```http
GET /schedule/input/latest
```

### Specific generation job
```http
GET /schedule/jobs/{job_id}
```

## Configuration

See `.env.example` for runtime configuration. Do not commit `.env` files, credentials, API keys, or private datasets.

## Testing

```bash
python -m unittest tests/test_smoke.py
```

GitHub Actions workflows also cover compilation, API import, input normalization, and a minimal scheduler run.

## Why this project is relevant

- Python
- FastAPI
- REST APIs
- Constraint-based scheduling
- Data normalization
- Backend integration
- Automated testing
- GitHub Actions / CI
- Performance optimization
- Long-running background jobs
- Structured academic data handling

## Status

The scheduling logic is preserved as-is. This public-facing cleanup focuses on documentation, safe configuration, and reproducible sample input.