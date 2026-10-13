"""API integration tests using only synthetic data and local temporary files."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from fastapi.testclient import TestClient


FIXTURE = Path(__file__).resolve().parents[1] / "sample_data" / "demo_academic_input.json"


class SchedulerAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._paths = (
            api.LATEST_SCHEDULE_FILE,
            api.GENERATION_STATUS_FILE,
            api.LATEST_INPUT_FILE,
        )
        root = Path(self.tmp.name)
        api.LATEST_SCHEDULE_FILE = root / "output.json"
        api.GENERATION_STATUS_FILE = root / "status.json"
        api.LATEST_INPUT_FILE = root / "input.json"
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.client = TestClient(api.app)
        self.created_job_ids = []

    def tearDown(self):
        for job_id in self.created_job_ids:
            job = api.jobs.get(job_id)
            if job:
                job["future"].result(timeout=15)
                with api.jobs_lock:
                    api.jobs.pop(job_id, None)
        (api.LATEST_SCHEDULE_FILE, api.GENERATION_STATUS_FILE, api.LATEST_INPUT_FILE) = self._paths
        self.client.close()
        self.tmp.cleanup()

    def test_health_and_default_status(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/schedule/status").json()["status"], "idle")
        self.assertEqual(self.client.get("/schedule/latest").status_code, 404)

    def test_post_generate_and_read_back_results(self):
        response = self.client.post("/schedule", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["success"], data)
        self.assertGreater(data["totalSessions"], 0)
        self.assertEqual(data["metadata"]["conflicts"], [])

        latest = self.client.get("/schedule/latest")
        self.assertEqual(latest.status_code, 200, latest.text)
        self.assertEqual(latest.json()["metadata"]["sourceSemesterId"], 999)

        snapshot = self.client.get("/schedule/input/latest")
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        self.assertEqual(snapshot.json()["payload"]["semesterId"], 999)

    def test_empty_input_reports_failure_without_500(self):
        invalid = self.payload.copy()
        invalid["regularCourses"] = []
        response = self.client.post("/schedule", json=invalid)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["success"])

    def test_backend_refresh_without_config_is_rejected(self):
        with patch.object(api, "BACKEND_AI_DATA_URL", ""):
            response = self.client.get("/schedule/from-backend?refresh=true")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("not configured", response.json()["detail"])

    def test_background_job_uses_only_synthetic_payload(self):
        with patch.object(api, "BACKEND_AI_DATA_URL", "https://example.invalid/synthetic"), \
             patch.object(api, "load_json_from_url", return_value=self.payload):
            response = self.client.get("/schedule/from-backend?refresh=true")
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["jobId"]
        self.created_job_ids.append(job_id)
        api.jobs[job_id]["future"].result(timeout=15)
        status = self.client.get("/schedule/status")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["status"], "completed")
        fetched = self.client.get(f"/schedule/jobs/{job_id}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertTrue(fetched.json()["result"]["success"])
        self.assertEqual(self.client.get("/schedule/latest").status_code, 200)


if __name__ == "__main__":
    unittest.main()
