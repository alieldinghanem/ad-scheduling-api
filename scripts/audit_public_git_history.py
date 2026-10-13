#!/usr/bin/env python3
"""Read-only pre-publication audit of reachable Git history.

Usage:
    git fetch --all --tags --prune
    python scripts/audit_public_git_history.py

Never prints university records or secret values. This is a screening tool,
not a guarantee that all confidential data has been removed. Run on a private
working clone, never in a public CI job with real historic data.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import PurePosixPath

GENERATED_NAMES = {
    "latest_schedule.json", "latest_schedule_status.json",
    "latest_input.json", "backend_input.json", "output_schedule.json",
    "generation_status.json",
}
DATA_EXTENSIONS = {".json", ".csv", ".tsv", ".txt", ".log", ".sqlite", ".sqlite3", ".db", ".sql"}
LIVE_HOST = re.compile(rb"https?://[a-z0-9.-]*(?:runasp[.]net|[.]internal|[.]local)(?=[/:?'#\s]|$)", re.I)
PERSON_FIELDS = re.compile(
    rb'["\x27](?:instructorName|studentName|studentId|nationalId|staffName)["\x27]\s*:\s*["\x27]([^"\x27]{2,150})["\x27]',
    re.I,
)
DEMO_PERSON = re.compile(rb"^(?:Instructor|Teaching Assistant|Student|Demo|Sample)\s*\d+\s*$", re.I)
SENSITIVE_PATH = re.compile(
    r"(^|/)(?:exports?|private|secrets?|credentials?|backups?|logs?)/",
    re.I,
)


def git(*args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args], capture_output=True, check=False, timeout=90
    )
    if check and result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed (exit {result.returncode})")
    return result.stdout


def main() -> int:
    try:
        git("rev-parse", "--is-inside-work-tree")
        refs = git("for-each-ref", "--format=%(refname)").decode().splitlines()
        rows = git("rev-list", "--objects", "--all").decode(
            "utf-8", errors="replace"
        ).splitlines()
    except Exception as exc:
        print(f"Cannot audit Git history: {exc}", file=sys.stderr)
        return 2

    if not refs or not rows:
        print("FAIL: no Git references/objects found; fetch complete private history.")
        return 2

    candidates: dict[str, set[str]] = defaultdict(set)
    path_count = 0
    for row in rows:
        if " " not in row:
            continue
        sha, path = row.split(" ", 1)
        if not path:
            continue
        path_count += 1
        candidates[sha].add(path)

    reasons: dict[str, set[str]] = defaultdict(set)
    inspected = 0
    for sha, paths in candidates.items():
        suffixes = {PurePosixPath(p).suffix.lower() for p in paths}
        needs_content_scan = bool(suffixes & DATA_EXTENSIONS) or any(
            p.endswith((".py", ".yml", ".yaml", ".toml", ".env", ".md")) for p in paths
        )
        for path in paths:
            filename = PurePosixPath(path).name
            if (filename in GENERATED_NAMES or filename == ".env"
                    or filename.startswith(".env.") and filename != ".env.example"):
                reasons["historic generated output or private env file"].add(path)
            if SENSITIVE_PATH.search(path):
                reasons["potentially private folder"].add(path)
        if not needs_content_scan:
            continue
        try:
            size = int(git("cat-file", "-s", sha).strip() or b"0")
            if size > 30_000_000:
                for path in paths:
                    reasons["large object needs manual review"].add(path)
                continue
            if git("cat-file", "-t", sha).strip() != b"blob":
                continue
            data = git("cat-file", "blob", sha)
            inspected += 1
            if LIVE_HOST.search(data):
                for path in paths:
                    reasons["historical private-looking backend URL"].add(path)
            if suffixes & DATA_EXTENSIONS:
                for match in PERSON_FIELDS.finditer(data):
                    value = match.group(1).strip()
                    if value and not DEMO_PERSON.match(value):
                        for path in paths:
                            reasons["populated personal-data fields"].add(path)
                        break
        except Exception:
            for path in paths:
                reasons["unreadable object needs manual review"].add(path)

    print(f"Checked {len(refs)} refs, {len(rows)} objects, "
          f"{path_count} historical path occurrences; "
          f"inspected {inspected} text/data blobs.")
    if not reasons:
        print("PASS: no matches to known risk heuristics.")
        print("NOTICE: still review GitHub PR refs, Actions artifacts, caches, "
              "repo ownership and manually verify private data is absent.")
        return 0

    print("BLOCKED: review before making this repository PUBLIC.")
    for reason, paths in sorted(reasons.items()):
        print(f"\n{reason}: {len(paths)} unique path(s)")
        for path in sorted(paths)[:30]:
            print(" -", path)
        if len(paths) > 30:
            print(f" ... and {len(paths) - 30} more")
    print("\nDo not force-push or change visibility until a private mirror "
          "backup, reviewed cleanup and final history verification are complete.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
