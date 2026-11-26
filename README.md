# ADEX Academic Distribution & Enrollment Expert

ADEX generates university timetables from course demand, instructor and teaching assistant availability, student-group schedules, and classroom capacity. It assigns lectures and practical sections to rooms and time slots and reports conflicts or sessions it cannot place.

**Production status.** The original ADEX platform is deployed and currently used to generate university timetables, as confirmed by the project author. The team built it as a Computer Science graduation project and received an **Excellent** grade. The broader platform also covers course registration and personalized scheduling for students who need academic support.

## My contribution

I developed the **Python scheduling engine** and integrated it with the **.NET backend**. The backend supplied JSON with student enrollment, instructors, teaching assistants, classroom capacity, and availability. I wrote the scheduling logic that turned those inputs into a university-wide timetable by assigning lectures and practical sections to rooms and time slots. The engine checks for conflicts and reports sessions it could not place.

## Project results

The original ADEX system is **running in production and used to generate university timetables**. It automates session placement and conflict checks, and gives scheduling staff a structured timetable and a list of unresolved sessions to review.

The production project used university data covering **42 courses, 102 instructors, 80 rooms, and 2,000+ students**. The team received an **Excellent** grade for the graduation project.

## Try the synthetic demo

The [demo input](sample_data/demo-input.json) contains fictional courses, instructors, and rooms. In a local copy of the source, run:

```powershell
python main.py sample_data/demo-input.json demo-output.json
```

The example generates two lectures and two practical sections for a fictional cohort of 42 students.

| Session | Time | Room |
| --- | --- | --- |
| Demo Computing lecture | Saturday 09:00–11:00 | DEMO-HALL |
| Demo Mathematics lecture | Saturday 11:00–13:00 | DEMO-HALL |
| Demo Computing practical, group A | Saturday 13:00–15:00 | DEMO-LAB-A |
| Demo Computing practical, group B | Saturday 15:00–17:00 | DEMO-LAB-B |

Open `demo-output.json` and check for `success: true` and `totalSessions: 4`.

## Stack and requirements

- Python 3.12
- FastAPI 0.115.12 and Uvicorn 0.34.2, pinned in [requirements.txt](requirements.txt)
- The command-line demo uses the Python standard library. Install the pinned packages to run the HTTP API.

## Run the API locally

Use Python 3.12. From the root of a local copy, install dependencies and start FastAPI:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open [Swagger UI](http://127.0.0.1:8000/docs) and submit the synthetic JSON to `POST /schedule`. The direct-input demo runs independently of the university backend.

## Environment variables

The local synthetic CLI and `POST /schedule` demo require no environment variables or credentials. `BACKEND_AI_DATA_URL` is for a separate authorized backend integration. See [.env.example](.env.example) for the configuration shape. Use only the local synthetic input when evaluating this demo.

## Implementation and testing

- [main.py](main.py) normalizes input and runs the scheduler from the command line.
- [scheduler.py](scheduler.py) assigns sessions and validates scheduling constraints.
- [api.py](api.py) exposes scheduling, status, and results through FastAPI.

```powershell
python -m unittest discover -s tests
```

## Data privacy

The demo input contains no university records. This repository is the legacy source repository, and its historical commits require a separate privacy review. Use the standalone portfolio edition for public sharing. Use the demo locally with synthetic data and keep institutional records, production configuration, and generated live schedules within the authorized environment.
