# ADEX — Public Release Procedure (Private Repository)

This checklist is intentionally conservative: **the code can be public only after the academic data in all relevant Git history has been removed and independently verified.** Do not publish production data, student/instructor identities, or university backend URLs.

## 1. Preserve the working system

- Before merging PR #3, check any existing university deployment: the private `BACKEND_AI_DATA_URL` must be configured there. The review branch deliberately has no live default backend source.
- The local demo runs with synthetic data. Real-data API endpoints are not authenticated; do **not** deploy them publicly.
- Freeze new contributions while preparing the history rewrite, and coordinate with anyone who may already have cloned the repository.

## 2. Create an offline, restricted backup

On a machine with GitHub access and Git installed:

```bash
git clone --mirror git@github.com:alieldinghanem/ad-scheduling-api.git adex-private-original.git
cd adex-private-original.git
git fsck --full
git bundle create ../adex-private-backup.bundle --all
cd ..
```

**Keep the mirror and bundle private and out of the public repository.** Verify the bundle with `git bundle verify adex-private-backup.bundle` from an appropriate existing repository, or by performing a test clone from it. Do not delete the backup while the migration is in progress.

## 3. Work only on a disposable clone

```bash
git clone ./adex-private-original.git adex-release-cleanup
cd adex-release-cleanup
git fetch --all --tags
python scripts/audit_public_git_history.py
```

The audit prints only paths and issue categories, not private record values. **Treat it as a risk-screening tool, not a complete data-loss-prevention assessment.** Find and examine *every* historical sensitive JSON, CSV, log, private source endpoint, secret, generated output, cache and relevant binary. Inspect all branches/tags and GitHub pull-request refs and workflow artifacts.

## 4. Prepare a reviewed history rewrite

Install `git-filter-repo` on the **local machine**, then prepare the full list of confidential paths and text replacements from the audit. A starting example is:

```bash
python -m pip install git-filter-repo
# EXAMPLE ONLY — extend this list after reviewing all historical data.
git filter-repo --force \
  --path latest_schedule.json \
  --path latest_input.json \
  --path output_schedule.json \
  --path backend_input.json \
  --path PUBLIC_RELEASE_AUDIT.md \
  --invert-paths
```

**Do not run this example blindly:** it cannot identify unknown file names or sanitize private URLs embedded in historical source files. Provide additional `--path`/`--path-glob` rules and approved `--replace-text` expressions as needed; verify current code is unchanged except for the documented privacy fixes. Review existing institution-specific course IDs and room constants with the project owner.

`git-filter-repo` may remove the configured `origin` remote as a safety precaution. Do not re-add and push until the results have been reviewed.

## 5. Verify, then coordinate the push

- Re-run the local audit on the rewritten full history.
- Search all reachable refs and *contents*, not only filenames, for university data, secrets, URLs and personal records.
- Confirm the final `main` snapshot includes only authorized source and synthetic datasets.
- Execute the complete local test suite and GitHub Actions on the final cleaned code.
- Confirm that history-rewrite consequences are accepted: commit hashes change and old clones/branches/PRs may become incompatible.
- Plan deletion/recreation of stale branches and PR references, and investigate GitHub Actions artifacts/caches; if necessary request GitHub Support help to remove retained sensitive historical objects.
- Only then coordinate an explicit, reviewed force-with-lease push for the intended heads and tags. Avoid an indiscriminate `git push --mirror --force`, which may target read-only GitHub refs or delete unintended refs.

## 6. Publish the source

Once every security gate is independently signed off:

1. Verify old public mirrors/forks, if any, do not retain protected data.
2. Check university/code intellectual-property rights and choose a LICENSE.
3. Confirm API endpoints connected to real data are authenticated before **public deployment**.
4. Open GitHub **Settings → General → Danger Zone → Change repository visibility → Make public** for the **existing** `ad-scheduling-api` repository, preserving its identity and star.
5. Update its GitHub description/topics and pin the repository to the profile.

**Release status now: NOT PUBLIC-READY.** PR #3 contains the reviewed functional improvements; the required history cleanup is not yet completed.
