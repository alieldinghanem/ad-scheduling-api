# Security and Privacy

This repository contains an academic timetabling engine. Treat input payloads and generated schedules as potentially sensitive because they may include instructors, student-group information, scheduling constraints, and internal identifiers.

## Public source code vs. public API deployment

Making the **source code** public is not the same as authorizing an Internet-accessible **production API**. The existing FastAPI endpoints do not currently enforce user authentication or authorization.

- **Do not expose a live API backed by actual university records to the public Internet** without access controls, data-minimization, transport security, and an operations/security review.
- The example configuration intentionally leaves `BACKEND_AI_DATA_URL` unset. Configure an authorized URL using your own private deployment environment if you need backend-fed scheduling.
- Use `sample_data/demo_academic_input.json` for public demos and CI. This fixture is synthetic.
- Do not commit `.env` files, credentials, instructor/student datasets, production payloads, log dumps, or generated timetable snapshots.
- Before changing the GitHub repository visibility, sanitize **all reachable Git history** (including obsolete branches/tags and PR references), then verify the result. Removing a file from the latest commit does not erase it from Git history.

## Reporting security problems

Report a suspected exposure privately to the repository owner. Avoid filing public issues that include real user records, internal access tokens, live data sources, or protected academic datasets.
