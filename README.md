# ADEX Academic Distribution & Enrollment Expert

ADEX generates university timetables from course demand, instructor and teaching assistant availability, student-group schedules, and classroom capacity. It assigns lectures and practical sections to rooms and time slots and reports conflicts or sessions it cannot place.

**Production status.** The original ADEX platform is deployed and currently used to generate university timetables, as confirmed by the project author. The team built it as a Computer Science graduation project and received an **Excellent** grade. The broader platform also covers course registration and personalized scheduling for students who need academic support.

## My contribution

I developed the **Python scheduling engine** and integrated it with the university platform's **.NET backend** through JSON. My work covered receiving enrollment, instructor, teaching assistant, and room data, assigning lectures and practical sections, and checking the resulting timetable for scheduling conflicts.

The production project used university data covering **42 courses, 102 instructors, 80 rooms, and more than 2,000 students**. These figures describe the original project scope.

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

## Run the API locally

Use Python 3.12. From the root of a local copy, install dependencies and start FastAPI:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open [Swagger UI](http://127.0.0.1:8000/docs) and submit the synthetic JSON to `POST /schedule`. The direct-input demo runs independently of the university backend.

## Implementation and testing

- [main.py](main.py) normalizes input and runs the scheduler from the command line.
- [scheduler.py](scheduler.py) assigns sessions and validates scheduling constraints.
- [api.py](api.py) exposes scheduling, status, and results through FastAPI.

```powershell
python -m unittest discover -s tests
```

## Data privacy

The demo input contains no university records. This repository is the legacy source repository, and its historical commits require a separate privacy review. Use the standalone portfolio edition for public sharing. Use the demo locally with synthetic data and keep institutional records, production configuration, and generated live schedules within the authorized environment.
