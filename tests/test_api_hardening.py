"""Focused reliability and opt-in security regressions; no institutional data."""
import json
import tempfile
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import api
from fastapi.testclient import TestClient


class APIHardeningTests(unittest.TestCase):
    def test_atomic_write_with_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.json"
            barrier = Barrier(6)

            def save(thread_id):
                barrier.wait(timeout=10)
                for index in range(30):
                    api._write_json_atomic(path, {"writer": thread_id, "index": index})
                return True

            with ThreadPoolExecutor(max_workers=6) as executor:
                self.assertTrue(all(executor.map(save, range(6))))
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(value["writer"], range(6))
            self.assertIn(value["index"], range(30))
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])

    def test_optional_api_key_protects_all_schedule_routes(self):
        with patch.object(api, "API_ACCESS_KEY", "synthetic-secret-for-test"):
            with TestClient(api.app) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                self.assertEqual(client.get("/schedule/status").status_code, 401)
                self.assertEqual(
                    client.get("/schedule/input/latest", headers={"X-API-Key": "wrong"}).status_code, 401
                )
                status = client.get(
                    "/schedule/status", headers={"X-API-Key": "synthetic-secret-for-test"}
                )
                self.assertEqual(status.status_code, 200, status.text)
                self.assertEqual(client.post("/schedule", json={}).status_code, 401)

    def test_no_key_keeps_local_demo_accessible(self):
        with patch.object(api, "API_ACCESS_KEY", ""):
            with TestClient(api.app) as client:
                self.assertEqual(client.get("/schedule/status").status_code, 200)

    def test_backend_snapshot_does_not_persist_private_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "snapshot.json"
            with patch.object(api, "LATEST_INPUT_FILE", file), patch.object(
                api, "BACKEND_AI_DATA_URL", "https://example.invalid/private?token=keep-private"
            ):
                api._save_latest_input({"semesterId": 999}, "testhash", 1)
                snapshot = json.loads(file.read_text(encoding="utf-8"))
            self.assertTrue(snapshot["source"]["backendConfigured"])
            self.assertNotIn("backendUrl", snapshot["source"])
            self.assertNotIn("keep-private", json.dumps(snapshot))

    def test_finished_future_registry_bounded_without_dropping_running_jobs(self):
        original_jobs = {}
        with api.jobs_lock:
            original_jobs.update(api.jobs)
            api.jobs.clear()
            for n in range(api.MAX_COMPLETED_JOBS + 8):
                future = Future()
                future.set_result({"test": n})
                api.jobs[f"completed-{n}"] = {"future": future, "createdAt": n}
            active = Future()
            api.jobs["still-running"] = {"future": active, "createdAt": 999}
        try:
            api._prune_completed_jobs()
            with api.jobs_lock:
                self.assertLessEqual(len(api.jobs), api.MAX_COMPLETED_JOBS + 1)
                self.assertIn("still-running", api.jobs)
                self.assertIn(
                    f"completed-{api.MAX_COMPLETED_JOBS + 7}", api.jobs
                )
        finally:
            with api.jobs_lock:
                api.jobs.clear()
                api.jobs.update(original_jobs)


if __name__ == "__main__":
    unittest.main()
