# Security and Privacy

This repository contains an academic timetabling engine. Treat input payloads and generated schedules as potentially sensitive because they may include instructors, student-group information, scheduling constraints, and internal identifiers.

## Public source code vs. public API deployment

Making the **source code** public is not the same as authorizing an Internet-accessible **production API**. The FastAPI scheduling and input-inspection endpoints support **opt-in** shared-key access control through `ADEX_API_KEY`. Without this configured secret, the endpoints remain **unauthenticated** for local synthetic demos. The application does not implement per-user authorization or rate limiting.

- **Do not expose a live API backed by actual university records to the public Internet** without strong access controls, data-minimization, transport security, and an operations/security review. A shared API key by itself is not sufficient for all production-security needs.
- When using the optional key, set `ADEX_API_KEY` only in a private deployment environment and supply it in the `X-API-Key` request header. Do not commit the secret or embed it in public frontend code.
- The example configuration intentionally leaves `BACKEND_AI_DATA_URL` unset. Configure an authorized URL using your own private deployment environment if you need backend-fed scheduling.
- Use `sample_data/demo_academic_input.json` for public demos and CI. This fixture is synthetic.
- Do not commit `.env` files, credentials, instructor/student datasets, production payloads, log dumps, or generated timetable snapshots.
- Before changing the GitHub repository visibility, sanitize **all reachable Git history** (including obsolete branches/tags and PR references), then verify the result. Removing a file from the latest commit does not erase it from Git history.

## Reporting security problems

Report a suspected exposure privately to the repository owner. Avoid filing public issues that include real user records, internal access tokens, live data sources, or protected academic datasets.
