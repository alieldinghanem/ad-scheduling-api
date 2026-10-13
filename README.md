# ADEX — Constraint-Based Academic Scheduling API

**University Timetable Generation | Python • FastAPI • Scheduling Algorithms • REST APIs**

ADEX is a university academic scheduling backend that builds lecture, section, and laboratory timetables from structured academic data. Instead of relying on manual timetable assignment, the system applies academic scheduling rules, allocates available resources, and reports conflicts or sessions that could not be scheduled.

Developed as **my graduation project**, ADEX received an **Excellent (Grade A)** evaluation. It was **successfully tested with real university academic scheduling data** and has been **used for actual timetable-generation workflows**, rather than being limited to a classroom prototype. The scheduling implementation remains in use, as reported by the project author.

The system was built for a university-scale scenario involving **2,000+ students**, courses, teaching staff, rooms, and student groups. These figures describe the original project scenario, not a benchmark for the included synthetic input.

> **Technical scope:** This is a **constraint-based scheduling and backend engineering project**, not a trained machine-learning model. The repository highlights scheduling logic, API design, data normalization, validation, and performance engineering.

## What the system does

- **Timetable generation:** Assigns lectures, sections, laboratories, and supported online sessions to suitable days and time slots.
- **Conflict prevention and detection:** Checks instructor, room, section, group, and cohort time overlaps.
- **Resource and capacity rules:** Takes instructor availability, room types, room capacity, group sizes, and section capacity into account.
- **Multiple academic tracks:** Includes scheduling rules for regular college courses, Arabic online courses, and APTECH courses.
- **Scheduling diagnostics:** Reports unscheduled activities, reasons, capacity issues, and detected conflicts rather than treating every run as successful.
- **API integration:** Accepts JSON through FastAPI and can consume academic data from a configurable backend endpoint.
- **Background processing:** Runs longer backend-driven generation tasks in a thread pool and exposes job IDs, status, and latest-result endpoints.
- **Performance work:** Adds memoization/caching for selected scheduling computations.

## Architecture

```text
Client / University Backend
          |
          v
     FastAPI (api.py)
          |
          +--> Direct scheduling request (POST /schedule)
          |
          +--> Configured backend fetch (GET /schedule/from-backend?refresh=true)
                          |
                          v
             Data normalization (main.py)
                          |
                          v
           SchedulingEngine (scheduler.py)
                - Resource assignment
                - Constraint checks
                - Scheduling heuristics
                - Conflict validation
                          |
                          v
          Generated timetable and diagnostics
                          |
                          v
     JSON output / job status / saved snapshots
```

## Technology

**Python 3.12**, **FastAPI**, **Uvicorn**, JSON-based REST APIs, constraint-based scheduling heuristics, Python standard-library concurrency, automated smoke tests, and GitHub Actions.

## Project structure

```text
api.py                         FastAPI routes, job execution, status and results
main.py                        Input normalization, JSON fetching, CLI entry point
scheduler.py                   Core scheduling and constraint validation
scheduler_performance.py       Selected scheduling performance optimizations
aptech_ara.py                  Arabic / APTECH schedule output processing
sitecustomize.py               Performance patch bootstrap
sample_data/sample_input.json  Synthetic schema example (no real records)
tests/test_smoke.py            Basic normalization and patch smoke tests
.github/workflows/            CI smoke-check workflows
.env.example                   Example runtime configuration
requirements.txt               Python dependencies
```

## Getting started

```bash
git clone https://github.com/alieldinghanem/ad-scheduling-api.git
cd ad-scheduling-api
python -m venv .venv
```

Activate the environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
uvicorn api:app --reload
```

- Local API: `http://127.0.0.1:8000`
- Swagger/OpenAPI: `http://127.0.0.1:8000/docs`
- Health endpoint: `GET /health`

### Using a JSON input

The project supports direct generation from JSON via `POST /schedule` and a CLI:

```bash
python main.py sample_data/sample_input.json output_schedule.json
```

**Important:** The committed `sample_input.json` deliberately has no courses, instructors, or rooms. It demonstrates the accepted top-level structure, **not a complete working timetable example**; an empty input will produce a failure/diagnostic response. For a meaningful generated timetable, provide a full **synthetic** dataset with matching courses, instructors, availability, and rooms.

### Relevant API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/schedule` | Generate a schedule from supplied JSON |
| `GET` | `/schedule/from-backend?refresh=true` | Fetch configured backend data and start a background job |
| `GET` | `/schedule/status` | Latest generation status |
| `GET` | `/schedule/jobs/{job_id}` | Status/result for a specific job |
| `GET` | `/schedule/latest` | Latest saved generated schedule |
| `GET` | `/schedule/input/latest` | Latest cached backend input snapshot |

> Backend-driven generation requires an accessible, authorized external data source configured via `BACKEND_AI_DATA_URL`. Its availability is not required to inspect the code or run synthetic direct-input tests.

## Testing

```bash
python -m unittest tests/test_smoke.py
```

The repository includes basic tests covering input normalization and the performance-patch installation. GitHub Actions workflows add compile and runtime smoke checks under their configured triggers.

**Current limitation:** The committed smoke tests do not constitute comprehensive end-to-end verification of scheduling quality or all conflict/capacity edge cases.

## Security and privacy

- Use only synthetic or appropriately authorized data for public demos, documentation, and tests.
- Never commit secrets, private university records, or generated schedules containing personal information.
- **The current API does not implement authentication for its scheduling and input-inspection routes.** Do **not** deploy it on an internet-accessible server with real academic data until access controls and data exposure are reviewed.
- Configuration examples are provided in `.env.example`; keep real credentials in a private environment.
- Before changing repository visibility to public, review **Git history as well as current files** for historic data or secrets.

## Project status and next improvements

The scheduling engine and API implementation are preserved as developed. Before presenting this repository as a publicly reproducible portfolio project, the main remaining work is:

1. Audit historic commits and generated-output data for confidentiality.
2. Add a realistic synthetic fixture producing a non-empty timetable.
3. Add automated integration/constraint tests for representative conflicts and room capacities.
4. Validate the documented quick start and CI workflows on a clean environment.
5. Add endpoint authentication/authorization before connecting a publicly reachable deployment to sensitive university data.

**ADEX demonstrates a graduation project evaluated as Excellent (Grade A), tested on real university scheduling inputs, and used in an operational timetable workflow.** It showcases constraint-based scheduling, REST API integration, diagnostics, and performance considerations.
