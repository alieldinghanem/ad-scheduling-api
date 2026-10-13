import unittest

import sitecustomize  # noqa: F401 - importing installs the performance patch
from main import normalize_payload
from scheduler import SchedulingEngine


class SchedulerSmokeTests(unittest.TestCase):
    def test_performance_patch_is_installed(self):
        self.assertTrue(
            getattr(SchedulingEngine, "_adex_performance_patch_installed", False)
        )

    def test_current_backend_shape_normalizes(self):
        payload = {
            "semesterId": 35,
            "days": ["Saturday"],
            "regularTimeSlots": ["09:00-11:00"],
            "targetGroupSize": 150,
            "sectionCapacity": 50,
            "regularCourses": [],
            "arabicCourses": [],
            "aptechCourses": [],
            "regularInstructors": [],
            "arabicInstructors": [],
            "aptechInstructors": [],
            "rooms": [],
            "studentGroups": [],
        }
        normalized = normalize_payload(payload)
        self.assertEqual(normalized["semesterId"], 35)
        self.assertEqual(normalized["targetGroupSize"], 150)
        self.assertEqual(normalized["sectionCapacity"], 50)


if __name__ == "__main__":
    unittest.main()
