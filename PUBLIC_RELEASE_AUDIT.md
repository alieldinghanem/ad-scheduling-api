# Public Release Audit — 2026-10-13

## Release decision: NOT PUBLIC-READY

The repository remains private and the public-release changes are isolated in PR #3. This review does **not** rewrite the scheduler or Git history.

## Confirmed blockers

1. **Historical real academic data:** `latest_schedule.json` (deleted on main in commit `038046978`) remains recoverable from history. The historical JSON contains populated `instructorName`, `instructorId`, group and timetable fields. The file must be removed from all Git refs and relevant history *before* switching visibility. Confirm any other old output files and tags as well. Rewriting history changes commit IDs and may affect existing clones/PRs; obtain explicit permission and arrange backup first.
2. **University backend configuration:** A live-looking university endpoint `nub-adex.runasp.net/api/Scheduling/ai-data` appears as an API default, in `.env.example`, and in an existing CI workflow. Review ownership/authorization, eliminate university-specific default coupling from the public source, and use opt-in environment configuration or a mock backend. Do not expose real backend payloads through public CI.
3. **Unprotected data routes:** FastAPI includes `GET /schedule/input/latest`, `GET /schedule/latest`, `GET /schedule/jobs/{job_id}`, `POST /schedule` and backend refresh routes with no evident access control. This is unsuitable for an internet-facing service using real university data. Publishing *code* and deploying an exposed API are different decisions.
4. **Full synthetic scheduling test fails:** GitHub Actions `Public demo validation`, run `38330366443`, passed installation/compilation and the FastAPI `GET /health` test, but the scheduler test raised `TypeError: unhashable type: 'dict'`. Trace: `scheduler_performance.py:cached_assigned_course_codes` -> `scheduler.py:_course_resource_lecture_cap`. The current monkey-patching code repeatedly assigns a shared closure variable `original` to different methods; this is a likely late-binding problem causing wrappers to invoke the wrong method. Verify and fix separately after approval, then rerun full CI. Do not claim functional demo validation while this test fails.
5. **Privacy and reproducibility:** Further complete review of all historical blobs/refs and a successful non-empty synthetic schedule is required.

## Current-file classification

| Path | Classification | Action |
|---|---|---|
| `scheduler.py` | REQUIRED FOR FUNCTIONALITY | Retain; check institution-specific identifiers, do not silently change scheduling logic |
| `api.py` | REQUIRED, SHOULD BE SANITIZED | Remove private default backend coupling; review authentication and public deployment |
| `main.py` | REQUIRED, SHOULD BE REVIEWED | Preserve normalization, review hardcoded course codes/configuration |
| `scheduler_performance.py` | REQUIRED, BUG FOUND | Preserve until separately approved fix |
| `aptech_ara.py` | REQUIRED | Retain and test |
| `sitecustomize.py` | REQUIRED | Retain; test initialization |
| `requirements.txt`, `.python-version` | SAFE TO PUBLIC | Retain after clean install validation |
| `.env.example` | SHOULD BE SANITIZED | Replace real backend URL with example placeholders |
| `.github/workflows/runtime-smoke-v3.yml` | SHOULD BE SANITIZED | Remove call to university data and fixed semester assumptions |
| `.github/workflows/scheduler-smoke.yml` | SAFE TO PUBLIC | Retain; may improve triggers |
| `.gitignore` | SAFE TO PUBLIC | Retain; historical tracked files are not erased by it |
| `sample_data/sample_input.json` | SAFE TO PUBLIC | Only a synthetic structural example; empty workload |
| `sample_data/demo_academic_input.json` | NEW, SYNTHETIC | Proposed synthetic multi-course fixture; execution not yet passing |
| `tests/test_smoke.py` | SAFE TO PUBLIC | Minimal checks only |
| `tests/test_synthetic_schedule.py` | NEW, TEST FAILS | Keep as regression test pending bug fix |
| `.github/workflows/public-demo-validation.yml` | NEW | Runs synthetic tests and FastAPI health check |
| `README.md` | DOCUMENTATION | Has Grade A, architecture, usage, and release risks; no production claim |
| Deleted `latest_schedule.json` in history | SHOULD BE REMOVED FROM ALL PUBLIC HISTORY | Contains populated instructor scheduling information |

## Work completed so far

- Added synthetic demonstration input, with fake instructor IDs and no student identities, to an isolated review branch.
- Added regression-style synthetic scheduling test.
- Added CI workflow for compilation, FastAPI health, and scheduler test.
- Created Draft PR #3. No merge, visibility change, secrets deletion, or Git history rewrite.
- Inspected GitHub Actions results and documented the reproducible scheduler error.

## Test evidence

| Test | Status | Evidence |
|---|---|---|
| Dependencies installed (GitHub Actions) | PASS | Run `38330366443` |
| Python files compile | PASS | Run `38330366443` |
| FastAPI `GET /health` | PASS | Run `38330366443` |
| Existing smoke checks | PASS in separate run | `38330366456` |
| Synthetic, non-empty scheduler generation | FAIL | `38330366443`, `TypeError` |
| Background job, full scheduling constraints, output endpoints | NOT VERIFIED | No end-to-end pass |
| Entire history cleared of sensitive data | NOT DONE | Historic generated schedule identified |
| Repo publicly visible | NO | Repository still private |

## Release prerequisites

- Decide and authorize how to rewrite history (backup, all refs, branches, PR impacts, force-push and stale clones).
- Review and remove all historic confidential inputs/outputs/secrets, including references in every reachable branch/tag.
- Replace university-specific URLs/configuration, and protect all endpoints before any deployment that handles private records.
- Resolve the memoization patch failure and confirm full synthetic scheduling test passes.
- Confirm license rights and add an open-source license if appropriate.
- Once verified, switch repository visibility to public through GitHub Settings.

**Do not make the repository public before these blockers are resolved.**
