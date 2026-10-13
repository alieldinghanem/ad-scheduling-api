"""Performance optimizations for the ADEX scheduling engine.

The scheduler repeatedly recomputes several values that are derived only from
normalized input data (course enrollments, instructor assignments and
availability).  This module memoizes those static calculations without caching
any dynamic placement state such as room/instructor/group busy checks.

Keeping the patch in a separate module avoids risky large edits to
``scheduler.py`` and makes the optimization easy to disable or revert.
"""

from __future__ import annotations

from functools import wraps
from typing import Any


def install_scheduler_performance_patch(SchedulingEngine):
    """Install safe memoization wrappers on expensive static calculations."""

    if getattr(SchedulingEngine, "_adex_performance_patch_installed", False):
        return SchedulingEngine

    original_init = SchedulingEngine.__init__

    @wraps(original_init)
    def patched_init(self, *args, **kwargs):
        # Some helper methods may be called during __init__, so the cache must
        # exist before the original constructor starts.
        self._adex_perf_cache = {}
        original_init(self, *args, **kwargs)

    SchedulingEngine.__init__ = patched_init

    def bucket(self, name: str) -> dict:
        cache = getattr(self, "_adex_perf_cache", None)
        if cache is None:
            cache = {}
            self._adex_perf_cache = cache
        return cache.setdefault(name, {})

    def blocked_key(self) -> tuple:
        # blocked_courses can change during resource pre-checks, so include its
        # current value in keys for calculations that depend on it.
        return tuple(sorted(getattr(self, "blocked_courses", set()) or set()))

    def method(name: str):
        return getattr(SchedulingEngine, name, None)

    # ------------------------------------------------------------------
    # Pure/static helpers
    # ------------------------------------------------------------------
    original = method("_assigned_course_codes")
    if original:
        @wraps(original)
        def cached_assigned_course_codes(self, instructor, _original=original):
            instructor_id = instructor.get("instructorId") if isinstance(instructor, dict) else None
            key = ("id", instructor_id) if instructor_id is not None else ("obj", id(instructor))
            cache = bucket(self, "assigned_course_codes")
            if key not in cache:
                cache[key] = _original(self, instructor)
            return cache[key]
        SchedulingEngine._assigned_course_codes = cached_assigned_course_codes

    original = method("_get_matching_instructors")
    if original:
        @wraps(original)
        def cached_matching_instructors(self, course_code, session_type, _original=original):
            key = (
                str(course_code or "").strip().upper(),
                str(session_type or "").strip().upper(),
            )
            cache = bucket(self, "matching_instructors")
            if key not in cache:
                cache[key] = _original(self, course_code, session_type)
            return cache[key]
        SchedulingEngine._get_matching_instructors = cached_matching_instructors

    original = method("_course_level_student_counts")
    if original:
        @wraps(original)
        def cached_course_level_student_counts(self, course, _original=original):
            code = self._course_code(course)
            if not code:
                return _original(self, course)
            cache = bucket(self, "course_level_student_counts")
            if code not in cache:
                cache[code] = _original(self, course)
            return cache[code]
        SchedulingEngine._course_level_student_counts = cached_course_level_student_counts

    original = method("_course_total_student_count")
    if original:
        @wraps(original)
        def cached_course_total_student_count(self, course, _original=original):
            code = self._course_code(course)
            if not code:
                return _original(self, course)
            cache = bucket(self, "course_total_student_count")
            if code not in cache:
                cache[code] = _original(self, course)
            return cache[code]
        SchedulingEngine._course_total_student_count = cached_course_total_student_count

    original = method("_course_relevant_student_count")
    if original:
        @wraps(original)
        def cached_course_relevant_student_count(self, course, _original=original):
            code = self._course_code(course)
            if not code:
                return _original(self, course)
            cache = bucket(self, "course_relevant_student_count")
            if code not in cache:
                cache[code] = _original(self, course)
            return cache[code]
        SchedulingEngine._course_relevant_student_count = cached_course_relevant_student_count

    original = method("_largest_general_room_capacity")
    if original:
        @wraps(original)
        def cached_largest_general_room_capacity(self, _original=original):
            cache = bucket(self, "largest_general_room_capacity")
            if "value" not in cache:
                cache["value"] = _original(self)
            return cache["value"]
        SchedulingEngine._largest_general_room_capacity = cached_largest_general_room_capacity

    original = method("_time_to_minutes")
    if original:
        @wraps(original)
        def cached_time_to_minutes(self, value, _original=original):
            try:
                hash(value)
            except Exception:
                return _original(self, value)
            cache = bucket(self, "time_to_minutes")
            if value not in cache:
                cache[value] = _original(self, value)
            return cache[value]
        SchedulingEngine._time_to_minutes = cached_time_to_minutes

    original = method("_slot_bounds")
    if original:
        @wraps(original)
        def cached_slot_bounds(self, slot, _original=original):
            if not isinstance(slot, str):
                return _original(self, slot)
            cache = bucket(self, "slot_bounds")
            if slot not in cache:
                cache[slot] = _original(self, slot)
            return cache[slot]
        SchedulingEngine._slot_bounds = cached_slot_bounds

    # ------------------------------------------------------------------
    # Expensive lecture-allocation calculations. These are static for a
    # specific blocked-course state, hence blocked_key is part of the key.
    # ------------------------------------------------------------------
    original = method("_instructor_regular_lecture_slot_count")
    if original:
        @wraps(original)
        def cached_instructor_regular_lecture_slot_count(self, instructor, course_code, _original=original):
            key = (
                instructor.get("instructorId") if isinstance(instructor, dict) else id(instructor),
                str(course_code or "").strip().upper(),
            )
            cache = bucket(self, "instructor_regular_lecture_slot_count")
            if key not in cache:
                cache[key] = _original(self, instructor, course_code)
            return cache[key]
        SchedulingEngine._instructor_regular_lecture_slot_count = cached_instructor_regular_lecture_slot_count

    original = method("_schedulable_lecture_courses_for_instructor")
    if original:
        @wraps(original)
        def cached_schedulable_lecture_courses_for_instructor(self, instructor, _original=original):
            key = (
                instructor.get("instructorId") if isinstance(instructor, dict) else id(instructor),
                blocked_key(self),
            )
            cache = bucket(self, "schedulable_lecture_courses_for_instructor")
            if key not in cache:
                cache[key] = tuple(_original(self, instructor))
            # Return a fresh list so callers cannot mutate the cached object.
            return list(cache[key])
        SchedulingEngine._schedulable_lecture_courses_for_instructor = cached_schedulable_lecture_courses_for_instructor

    original = method("_other_doctor_lecture_slot_count")
    if original:
        @wraps(original)
        def cached_other_doctor_lecture_slot_count(self, current_instructor, course_code, _original=original):
            key = (
                current_instructor.get("instructorId") if isinstance(current_instructor, dict) else id(current_instructor),
                str(course_code or "").strip().upper(),
                blocked_key(self),
            )
            cache = bucket(self, "other_doctor_lecture_slot_count")
            if key not in cache:
                cache[key] = _original(self, current_instructor, course_code)
            return cache[key]
        SchedulingEngine._other_doctor_lecture_slot_count = cached_other_doctor_lecture_slot_count

    original = method("_instructor_course_lecture_slot_share")
    if original:
        @wraps(original)
        def cached_instructor_course_lecture_slot_share(self, instructor, course_code, _original=original):
            key = (
                instructor.get("instructorId") if isinstance(instructor, dict) else id(instructor),
                str(course_code or "").strip().upper(),
                blocked_key(self),
            )
            cache = bucket(self, "instructor_course_lecture_slot_share")
            if key not in cache:
                cache[key] = _original(self, instructor, course_code)
            return cache[key]
        SchedulingEngine._instructor_course_lecture_slot_share = cached_instructor_course_lecture_slot_share

    original = method("_course_lecture_instructor_slot_count")
    if original:
        @wraps(original)
        def cached_course_lecture_instructor_slot_count(self, course, _original=original):
            code = self._course_code(course)
            if not code:
                return _original(self, course)
            key = (code, blocked_key(self))
            cache = bucket(self, "course_lecture_instructor_slot_count")
            if key not in cache:
                cache[key] = _original(self, course)
            return cache[key]
        SchedulingEngine._course_lecture_instructor_slot_count = cached_course_lecture_instructor_slot_count

    original = method("_course_desired_lecture_count")
    if original:
        @wraps(original)
        def cached_course_desired_lecture_count(self, course_code, _original=original):
            key = (str(course_code or "").strip().upper(), blocked_key(self))
            cache = bucket(self, "course_desired_lecture_count")
            if key not in cache:
                cache[key] = _original(self, course_code)
            return cache[key]
        SchedulingEngine._course_desired_lecture_count = cached_course_desired_lecture_count

    original = method("_course_resource_lecture_cap")
    if original:
        @wraps(original)
        def cached_course_resource_lecture_cap(self, course_code, _original=original):
            key = (str(course_code or "").strip().upper(), blocked_key(self))
            cache = bucket(self, "course_resource_lecture_cap")
            if key not in cache:
                cache[key] = _original(self, course_code)
            return cache[key]
        SchedulingEngine._course_resource_lecture_cap = cached_course_resource_lecture_cap

    SchedulingEngine._adex_performance_patch_installed = True
    return SchedulingEngine
