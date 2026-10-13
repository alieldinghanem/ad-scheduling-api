# Public Release Audit — 2026-10-13

## Release decision: NOT PUBLIC-READY

The repository remains private and the public-release changes are isolated in PR #3. This review does **not** rewrite the scheduler or Git history.

## Confirmed blockers

1. **Historical real academic data:** `latest_schedule.json` (deleted on main in commit `038046978`) remains recoverable from history. The historical JSON contains populated `instructorName`, `instructorId`, group and timetable fields. The file must be removed from all Git refs and relevant history *before* switching visibility. Confirm any other old output files and tags as well. Rewriting history changes commit IDs and may affect existing clones/PRs; obtain explicit permission and arrange backup first.
2. **University backend integration sanitization IN REVIEW:** The live-looking endpoint `[redacted institutional backend URL]` appeared in the original default, example env, and CI. On the review branch, it was replaced with opt-in `BACKEND_AI_DATA_URL`, an empty `.env.example` value, and a synthetic-input-only workflow. This remains in `main` and previous Git history until review/merge and history cleaning. Never expose university source payloads in public CI.
3. **Unprotected data routes:** FastAPI includes `GET /schedule/input/latest`, `GET /schedule/latest`, `GET /schedule/jobs/{job_id}`, `POST /schedule` and backend refresh routes with no evident access control. This is unsuitable for an internet-facing service using real university data. Publishing *code* and deploying an exposed API are different decisions.
4. **Scheduler caching issue FIXED on review branch:** Previous synthetic test (run `38330366443`) failed with `TypeError: unhashable type: 'dict'` due to late binding of `original` across memoization closures. Bound each method to its original callable via a default argument in `scheduler_performance.py`; **six tests now pass** in GitHub Actions (run `38331158477`), including non-empty synthetic scheduling and conflict checks. This fix is limited to the review branch and awaits merging. No scheduling constraint rules were changed.
5. **Privacy and reproducibility:** Further complete review of all historical blobs/refs and a successful non-empty synthetic schedule is required.

## Current-file classification

| Path | Classification | Action |
|---|---|---|
| `scheduler.py` | REQUIRED FOR FUNCTIONALITY | Retain; check institution-specific identifiers, do not silently change scheduling logic |
| `api.py` | REQUIRED, SANITIZED ON BRANCH | Default endpoint removed; configured backend remains supported. Authentication still needed before internet deployment |
| `main.py` | REQUIRED, SHOULD BE REVIEWED | Preserve normalization, review hardcoded course codes/configuration |
| `scheduler_performance.py` | REQUIRED, FIXED ON BRANCH | Corrected Python closure capture in caching wrappers; no scheduling rules changed |
| `aptech_ara.py` | REQUIRED | Retain and test |
| `sitecustomize.py` | REQUIRED | Retain; test initialization |
| `requirements.txt`, `.python-version` | SAFE TO PUBLIC | Retain after clean install validation |
| `.env.example` | SANITIZED ON BRANCH | Real backend URL replaced by blank opt-in variable |
| `.github/workflows/runtime-smoke-v3.yml` | SANITIZED ON BRANCH | Replaced live fetch with synthetic input; CI rerun pending at time of edit |
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
- Fixed Python late-bound method wrappers in the performance memoization patch; validated six tests in Actions.
- Removed the original university URL from current review-branch API defaults and example configuration; changed one CI workflow to use a synthetic source.
- Created Draft PR #3. No merge, visibility change, secrets deletion, or Git history rewrite.
- Inspected GitHub Actions results and documented the reproducible scheduler error.

## Test evidence

| Test | Status | Evidence |
|---|---|---|
| Dependencies installed (GitHub Actions) | PASS | Run `38330366443` |
| Python files compile | PASS | Run `38330366443` |
| FastAPI `GET /health` | PASS | Run `38330366443` |
| Existing smoke checks | PASS in separate run | `38330366456` |
| Synthetic, non-empty scheduler generation | PASS on review branch | `38331158477`: six Python unittest checks OK |
| Background job, full scheduling constraints, output endpoints | NOT VERIFIED | No end-to-end pass |
| Entire history cleared of sensitive data | NOT DONE | Historic generated schedule identified |
| Repo publicly visible | NO | Repository still private |

## Release prerequisites

- Decide and authorize how to rewrite history (backup, all refs, branches, PR impacts, force-push and stale clones).
- Review and remove all historic confidential inputs/outputs/secrets, including references in every reachable branch/tag.
- Replace university-specific URLs/configuration, and protect all endpoints before any deployment that handles private records.
- Review and merge the verified memoization correction and confirm synthetic scheduling tests still pass after clean history.
- Confirm license rights and add an open-source license if appropriate.
- Once verified, switch repository visibility to public through GitHub Settings.

**Do not make the repository public before these blockers are resolved.**
