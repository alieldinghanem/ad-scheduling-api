"""End-to-end synthetic scheduling checks; no real university data."""
import json
import unittest
from pathlib import Path

import sitecustomize  # noqa: F401
from main import run_scheduler

FIXTURE = Path(__file__).resolve().parents[1] / "sample_data" / "demo_academic_input.json"


class DemoSchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.result = run_scheduler(cls.payload)

    def test_fixture_is_synthetic_and_complete(self):
        self.assertEqual(self.payload["semesterId"], 999)
        self.assertEqual(len(self.payload["regularCourses"]), 2)
        self.assertEqual(len(self.payload["regularInstructors"]), 2)
        self.assertEqual(len(self.payload["rooms"]), 3)
        self.assertNotIn("http://", FIXTURE.read_text(encoding="utf-8").lower())
        self.assertNotIn("https://", FIXTURE.read_text(encoding="utf-8").lower())

    def test_nonempty_schedule(self):
        self.assertIsInstance(self.result, dict)
        self.assertGreater(self.result.get("totalSessions", 0), 0)
        self.assertGreater(self.result.get("totalGroups", 0), 0)

    def test_no_conflicts_or_unscheduled_demands(self):
        metadata = self.result.get("metadata", {})
        self.assertEqual(metadata.get("conflicts"), [], metadata)
        self.assertEqual(metadata.get("unscheduledCount"), 0, metadata)
        self.assertTrue(self.result.get("success"), self.result)

    def test_output_serializable(self):
        json.dumps(self.result, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
