import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple


ARABIC_ONLINE_COURSES = set()
ONLINE_RECORDED_COURSES = set()
IGNORED_ONLINE_COURSES = set()
DISPLAY_ONLY_COURSES = set()
PROJECT_COURSES = set()
PROJECT_DEFAULT_LEVEL = 4
PROJECT_DISPLAY_DETAILS = {}
PHYSICS_LAB_ROOM_IDS = {79, 80}
PHYSICS_LAB_ROOM_NUMBERS = {"2201", "2202"}
MIN_EFFECTIVE_ROOM_CAPACITY = 150
ROOM_CAPACITY_OVERRIDES = {}
ROOM_TYPE_OVERRIDES = {}
DEFAULT_LECTURE_DURATION_MINUTES = 120
DEFAULT_SECTION_DURATION_MINUTES = 120
SPECIAL_LECTURE_DURATIONS = {"CS214": 60, "ETS401": 60}
SPECIAL_SECTION_DURATIONS = {"CS214": 60}
DEFAULT_DAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
DEFAULT_REGULAR_SLOTS = ["09:00-11:00", "11:00-13:00", "13:00-15:00", "15:00-17:00"]
DEFAULT_ONLINE_SLOTS = ["17:00-19:00"]


class SchedulingEngine:
    def __init__(self, input_data: dict):
        self.input_data = input_data or {}
        self.session_counter = 0

        self.arabic_online_courses = self._code_set_setting(
            ("arabicOnlineCourses", "arabicCourseCodes"),
            ARABIC_ONLINE_COURSES,
        )
        self.arabic_online_courses.update(
            self._codes_from_course_items(self.input_data.get("arabicCourses"))
        )
        self.online_recorded_courses = self._code_set_setting(
            ("onlineRecordedCourses", "recordedOnlineCourseCodes"),
            self.arabic_online_courses,
        )
        self.ignored_online_courses = self._code_set_setting(
            ("ignoredOnlineCourses", "ignoredCourseCodes"),
            IGNORED_ONLINE_COURSES,
        )
        self.display_only_courses = self._code_set_setting(
            ("displayOnlyCourses", "displayOnlyCourseCodes"),
            DISPLAY_ONLY_COURSES,
        )
        self.project_courses = self._code_set_setting(
            ("projectCourses", "projectCourseCodes"),
            PROJECT_COURSES,
        )
        self.project_courses.update(
            self._codes_from_course_items(self.input_data.get("projectCourses"))
        )
        self.project_default_level = max(
            1,
            self._safe_int(self.input_data.get("projectDefaultLevel"), PROJECT_DEFAULT_LEVEL),
        )
        self.project_display_details = self._project_display_details_setting()
        self.physics_lab_room_ids = self._int_set_setting(
            ("physicsLabRoomIds",),
            PHYSICS_LAB_ROOM_IDS,
        )
        self.physics_lab_room_numbers = self._text_set_setting(
            ("physicsLabRoomNumbers",),
            PHYSICS_LAB_ROOM_NUMBERS,
        )
        self.min_effective_room_capacity = max(
            0,
            self._safe_int(
                self.input_data.get("minEffectiveRoomCapacity"),
                MIN_EFFECTIVE_ROOM_CAPACITY,
            ),
        )
        self.room_capacity_overrides = self._int_dict_setting(
            ("roomCapacityOverrides",),
            ROOM_CAPACITY_OVERRIDES,
        )
        self.room_type_overrides = self._text_dict_setting(
            ("roomTypeOverrides",),
            ROOM_TYPE_OVERRIDES,
        )
        self.special_lecture_durations = self._int_dict_setting(
            ("specialLectureDurations",),
            SPECIAL_LECTURE_DURATIONS,
        )
        self.special_section_durations = self._int_dict_setting(
            ("specialSectionDurations",),
            SPECIAL_SECTION_DURATIONS,
        )

        self.days = self._list_or_default(self.input_data.get("days"), DEFAULT_DAYS)
        self.regular_slots = self._list_or_default(
            self.input_data.get("regularTimeSlots"), DEFAULT_REGULAR_SLOTS
        )
        self.online_slots = self._list_or_default(
            self.input_data.get("arabicOnlineTimeSlots")
            or self.input_data.get("onlineTimeSlots"),
            DEFAULT_ONLINE_SLOTS,
        )

        self.max_lecture_group_size = self._safe_int(
            self.input_data.get("maxLectureGroupSize", self.input_data.get("targetGroupSize")),
            150,
        )
        self.explicit_max_lecture_group_size = self._safe_int(
            self.input_data.get("maxLectureGroupSize"),
            None,
        )
        if self.explicit_max_lecture_group_size is not None and self.explicit_max_lecture_group_size <= 0:
            self.explicit_max_lecture_group_size = None
        self.allow_online_lecture_overflow = False
        self.max_section_size = self._safe_int(
            self.input_data.get("maxSectionSize", self.input_data.get("sectionCapacity")),
            50,
        )
        self.min_lecture_group_size = max(
            1,
            self._safe_int(
                self.input_data.get("minLectureGroupSize"),
                self.max_section_size,
            ),
        )
        self.min_sections_per_lecture_group = max(
            1,
            self._safe_int(self.input_data.get("minSectionsPerLectureGroup"), 1),
        )
        self.target_group_size = self.max_lecture_group_size
        self.section_capacity = self.max_section_size

        self.online_course_codes = self._extract_online_course_codes(
            list(self.input_data.get("onlineCourses") or [])
            + list(self.input_data.get("arabicCourses") or [])
        )

        self.courses = self._normalize_courses()
        self.aptech_courses = self._normalize_aptech_courses()
        raw_instructors = []
        raw_instructors.extend(self._instructors_with_source(self.input_data.get("instructors"), "all"))
        raw_instructors.extend(
            self._instructors_with_source(self.input_data.get("regularInstructors"), "college")
        )
        raw_instructors.extend(
            self._instructors_with_source(self.input_data.get("arabicInstructors"), "arabic")
        )
        self.instructors = self._normalize_instructors(raw_instructors)
        self.aptech_instructors = self._normalize_instructors(
            self.input_data.get("aptechInstructors", [])
        )
        self.rooms = self._normalize_rooms(self.input_data.get("rooms", []))

        self.group_busy = set()
        self.cohort_busy = set()
        self.section_busy = set()
        self.instructor_busy = set()
        self.room_busy = set()

        self.group_schedules: Dict[str, List[dict]] = defaultdict(list)
        self.instructor_schedules: Dict[int, List[dict]] = defaultdict(list)
        self.room_schedules: Dict[int, List[dict]] = defaultdict(list)

        self.group_sizes: Dict[str, int] = {}
        self.group_details: Dict[str, dict] = {}
        self.course_group_sizes: Dict[str, Dict[str, int]] = defaultdict(dict)

        self.unscheduled_reasons: List[str] = []
        self.warnings: List[str] = []
        self.skipped_courses: Dict[str, str] = {}
        self.blocked_courses: set = set()

        self._filter_courses_without_required_staff()

    def generate_schedule(self) -> dict:
        if not self.courses:
            return self._empty_fail("No schedulable courses were found.")

        if self._has_instructor_dependent_courses() and not self.instructors:
            return self._empty_fail("No instructors were found.")

        if not self.days or not self.regular_slots:
            return self._empty_fail("No days or regular time slots were found.")

        if self._has_offline_courses() and not self.rooms:
            return self._empty_fail("No rooms were found for offline courses.")

        self._create_level_groups()
        self._create_project_groups()
        self._precheck_course_resources()

        lecture_demands, section_demands, online_demands = self._build_demands()

        self._schedule_demands(lecture_demands)
        self._schedule_demands(section_demands)
        self._schedule_demands(online_demands)
        self._schedule_arabic_online_courses()
        self._schedule_project_courses()

        aptech_courses_output = self._build_aptech_courses_output()
        college_courses_output = self._build_course_sessions_output("college")
        arabic_courses_output = self._build_course_sessions_output("arabic")
        conflicts = self.validate_no_conflicts()
        conflicts.extend(self.validate_academic_constraints())

        aptech_session_count = sum(
            self._safe_int(course.get("totalSessions"), 0)
            for course in aptech_courses_output
        )
        total_sessions = (
            sum(len(v) for v in self.group_schedules.values())
            + aptech_session_count
        )
        total_groups = len(self.group_details)
        aptech_unscheduled = [
            course
            for course in aptech_courses_output
            if course.get("status") != "SCHEDULED"
        ]
        unscheduled_count = (
            len(self.unscheduled_reasons)
            + len(self.skipped_courses)
            + len(aptech_unscheduled)
        )
        success = (
            not conflicts
            and unscheduled_count == 0
            and total_groups > 0
            and total_sessions > 0
        )

        if success:
            message = "Schedule generated successfully"
        elif total_groups == 0 or total_sessions == 0:
            message = "No regular schedule generated; check course instructors, student counts, and availabilities"
        else:
            message = "Schedule generated with issues"

        group_schedules_output = self._build_group_schedules_output()
        student_group_schedules_output = self._build_student_group_schedules_output()
        instructor_schedules_output = self._simplify_instructor_schedules_output(
            self._build_instructor_schedules_output()
        )
        room_schedules_output = self._simplify_room_schedules_output(
            self._build_room_schedules_output()
        )

        return {
            "success": success,
            "message": message,
            "scheduleUrl": self.input_data.get("scheduleUrl") or self.input_data.get("outputScheduleUrl"),

            "courseTable": self._build_course_table_output(),

            # Keep college and Arabic simplified for frontend readability.
            "collegeCourses": self._simplify_courses_output(college_courses_output),
            "arabicCourses": self._simplify_courses_output(arabic_courses_output),

            # Keep Aptech raw because it has assignedInstructorId, dayOfWeek, timeSlot, and sessions.
            "aptechCourses": aptech_courses_output,

            "schedulesByType": {
                "college": self._simplify_courses_output(college_courses_output),
                "arabic": self._simplify_courses_output(arabic_courses_output),
                "aptech": aptech_courses_output,
            },

            "optimizationSummary": self._build_optimization_summary(),

            "groupSchedules": group_schedules_output,
            "studentGroupSchedules": student_group_schedules_output,
            "instructorSchedules": instructor_schedules_output,
            "roomSchedules": room_schedules_output,

            "totalSessions": total_sessions,
            "totalGroups": total_groups,
            "totalStudentGroups": len(student_group_schedules_output),

            "metadata": {
                "semesterId": self.input_data.get("semesterId"),
                "unscheduledCount": unscheduled_count,
                "unscheduledReasons": self.unscheduled_reasons,
                "warnings": self.warnings,
                "capacityIssues": self._build_capacity_issues_output(),
                "conflicts": conflicts,
                "unscheduledAptechCourses": aptech_unscheduled,
                "skippedCourses": [
                    {"courseCode": code, "reason": reason}
                    for code, reason in sorted(self.skipped_courses.items())
                ],
            },
        }

    def _schedule_demands(self, demands: List[dict]) -> None:
        pending = list(demands)

        if pending and all(demand.get("kind") == "SECTION_BUNDLE" for demand in pending):
            self._schedule_section_bundles_balanced(pending)
            return

        while pending:
            pending.sort(key=self._demand_priority_key)
            demand = pending.pop(0)

            if demand["kind"] == "SECTION_BUNDLE":
                ok = self._schedule_section_bundle(demand)
            else:
                ok = self._schedule_single_session(demand)

            if not ok and not demand.get("_reason_added"):
                reason = self._diagnose_unscheduled_demand(demand)
                self.unscheduled_reasons.append(reason)

    def _schedule_section_bundles_balanced(self, demands: List[dict]) -> None:
        by_course = defaultdict(list)
        for demand in demands:
            by_course[demand.get("courseCode") or ""].append(demand)

        ordered_courses = sorted(
            by_course.values(),
            key=lambda items: min(self._demand_priority_key(item) for item in items),
        )

        for course_demands in ordered_courses:
            self._schedule_course_section_bundles_balanced(course_demands)

    def _schedule_course_section_bundles_balanced(self, demands: List[dict]) -> None:
        states = []

        for demand in demands:
            section_sizes = self._distribute_group_to_sections(
                demand["groupSize"],
                demand["targetSections"],
                self.max_section_size,
            )
            instructors = self._get_matching_instructors(demand["courseCode"], "SECTION")
            rooms = self._get_matching_rooms("SECTION", demand["labType"], 1, False)

            state = {
                "demand": demand,
                "sectionSizes": section_sizes or [],
                "instructors": instructors,
                "rooms": rooms,
                "scheduled": 0,
                "blocked": False,
                "fallbackUsed": False,
            }
            states.append(state)

            if not section_sizes:
                self._add_unscheduled(
                    demand,
                    f"Section capacity is not enough for {demand['courseCode']} group={demand['groupId']}",
                )
                state["blocked"] = True
            elif not instructors:
                self._add_unscheduled(
                    demand,
                    f"No TA/instructor for {demand['courseCode']} sections group={demand['groupId']}",
                )
                state["blocked"] = True
            elif not rooms:
                self._add_unscheduled(
                    demand,
                    f"No suitable rooms for {demand['courseCode']} sections group={demand['groupId']} labType={demand['labType']}",
                )
                state["blocked"] = True

        while True:
            active = [
                state
                for state in states
                if not state["blocked"]
                and state["scheduled"] < len(state["sectionSizes"])
            ]
            if not active:
                break

            progress = False
            active.sort(key=self._section_state_priority_key)

            for state in active:
                if state["blocked"] or state["scheduled"] >= len(state["sectionSizes"]):
                    continue

                if self._schedule_next_section_for_state(state):
                    progress = True
                else:
                    state["blocked"] = True

            if not progress:
                break

        for state in states:
            demand = state["demand"]
            if demand.get("_reason_added"):
                continue

            scheduled = state["scheduled"]
            total = len(state["sectionSizes"])
            if scheduled <= 0:
                self._add_unscheduled(
                    demand,
                    self._diagnose_partial_sections(demand, scheduled, total, 1),
                )
                continue

            if state.get("fallbackUsed"):
                self.warnings.append(
                    f"Used a general room fallback for {demand['courseCode']} sections group={demand['groupId']} because lab rooms were not enough."
                )

            if scheduled != total:
                self.warnings.append(
                    self._diagnose_partial_sections(
                        demand,
                        scheduled,
                        total,
                        max(1, demand.get("minSections", 1)),
                    )
                )

    def _section_state_priority_key(self, state: dict) -> Tuple[int, int, int, int, str, str]:
        demand = state["demand"]
        remaining = len(state["sectionSizes"]) - state["scheduled"]
        return (
            state["scheduled"],
            self._demand_candidate_placement_count(demand),
            -remaining,
            -self._safe_int(demand.get("groupSize"), 0),
            demand.get("courseCode") or "",
            demand.get("groupId") or "",
        )

    def _schedule_next_section_for_state(self, state: dict) -> bool:
        demand = state["demand"]
        section_index = state["scheduled"] + 1
        section_demand = self._build_section_demand(
            demand,
            section_index,
            state["sectionSizes"][state["scheduled"]],
            demand["labType"],
        )

        if self._schedule_one_section(
            section_demand,
            state["instructors"],
            state["rooms"],
        ):
            state["scheduled"] += 1
            return True

        if demand.get("labType") == "LAB_ONLY":
            fallback_rooms = self._get_matching_rooms("SECTION", "GENERAL_LAB", 1, False)
            if fallback_rooms and self._schedule_one_section(
                {**section_demand, "labType": "GENERAL_LAB"},
                state["instructors"],
                fallback_rooms,
            ):
                state["scheduled"] += 1
                state["fallbackUsed"] = True
                return True

        return False

    def _build_section_demand(
        self,
        demand: dict,
        section_index: int,
        section_size: int,
        lab_type: str,
    ) -> dict:
        group_id = demand["groupId"]
        return {
            "kind": "SECTION",
            "sessionType": "SECTION",
            "courseCode": demand["courseCode"],
            "courseName": demand["courseName"],
            "groupId": group_id,
            "studentCount": section_size,
            "sectionId": self._section_label(group_id, section_index),
            "isOnline": False,
            "labType": lab_type,
        }

    def _demand_priority_key(self, demand: dict) -> Tuple[int, int, int, int, int, str, str]:
        placements = self._demand_candidate_placement_count(demand)
        if placements <= 0:
            placements = 999_999

        course_code = demand.get("courseCode") or ""
        session_type = demand.get("sessionType") or ""
        already_scheduled = self._scheduled_course_session_count(course_code, session_type)
        course_total_students = self._course_total_student_count(self.courses.get(course_code, {}))

        return (
            placements,
            -course_total_students,
            already_scheduled,
            -self._safe_int(demand.get("difficulty"), 0),
            -self._safe_int(demand.get("studentCount", demand.get("groupSize")), 0),
            course_code,
            demand.get("groupId") or "",
        )

    def _course_total_student_count(self, course: dict) -> int:
        total = self._safe_int(course.get("totalStudentCount"), 0)
        if total > 0:
            return total

        return sum(self._safe_int(value, 0) for value in self._course_level_student_counts(course).values())

    def _scheduled_course_session_count(self, course_code: str, session_type: str) -> int:
        count = 0

        for sessions in self.group_schedules.values():
            for session in sessions:
                if session.get("courseCode") != course_code:
                    continue

                if session_type == "SECTION" and session.get("sessionType") in {"SECTION", "PROJECT"}:
                    count += 1
                elif session_type != "SECTION" and session.get("sessionType") == session_type:
                    count += 1

        return count

    def _demand_candidate_placement_count(self, demand: dict) -> int:
        if demand.get("kind") == "SECTION_BUNDLE":
            return self._section_bundle_candidate_placement_count(demand)

        course_code = demand["courseCode"]
        group_id = demand["groupId"]
        is_online = demand.get("isOnline") is True
        instructors = self._get_matching_instructors(course_code, "LECTURE")
        rooms = self._get_matching_rooms("LECTURE", None, demand["studentCount"], is_online)
        if not is_online:
            rooms = self._get_lecture_room_candidates(
                demand["studentCount"],
                allow_capacity_overflow=True,
            )

        if not instructors and not demand.get("isArabicOnline"):
            return 0

        if not is_online and not rooms:
            return 0

        slots = (
            self._online_slots_for_course(course_code)
            if is_online
            else self._preferred_slots_for_course(course_code, "LECTURE")
        )

        count = 0
        for day in self._preferred_days_for_group(group_id):
            for slot in self._preferred_slots_for_group_on_day(group_id, day, slots):
                if self._has_group_time_conflict(group_id, day, slot, demand):
                    continue

                free_instructors = 1 if not instructors else sum(
                    1
                    for instructor in instructors
                    if self._can_use_instructor(instructor, day, slot, demand)
                )
                if free_instructors <= 0:
                    continue

                if is_online:
                    count += free_instructors
                    continue

                free_rooms = sum(1 for room in rooms if self._can_use_room(room, day, slot))
                count += min(free_instructors, free_rooms)

        return count

    def _section_bundle_candidate_placement_count(self, demand: dict) -> int:
        course_code = demand["courseCode"]
        group_id = demand["groupId"]
        lab_type = demand.get("labType")
        instructors = self._get_matching_instructors(course_code, "SECTION")
        rooms = self._get_matching_rooms("SECTION", lab_type, 1, False)

        if not instructors or not rooms:
            return 0

        slots = self._preferred_slots_for_course(course_code, "SECTION")
        count = 0

        for day in self._preferred_days_for_group(group_id):
            for slot in self._preferred_slots_for_group_on_day(group_id, day, slots):
                if self._has_group_time_conflict(group_id, day, slot, demand):
                    continue

                free_instructors = sum(
                    1
                    for instructor in instructors
                    if self._can_use_instructor(
                        instructor,
                        day,
                        slot,
                        {
                            "sessionType": "SECTION",
                            "courseCode": course_code,
                            "isOnline": False,
                            "labType": lab_type,
                        },
                    )
                )
                free_rooms = sum(1 for room in rooms if self._can_use_room(room, day, slot))
                count += min(free_instructors, free_rooms)

        return count

    def _precheck_course_resources(self) -> None:
        # Groups and sections are now sized by the resource slots we can actually place.
        # The old precheck blocked courses when student-based ideal sections were not possible.
        return

    def _schedule_project_courses(self) -> None:
        for code, course in sorted(
            self.courses.items(),
            key=lambda item: self._course_output_sort_key(item[1]),
        ):
            if not self._is_project_course(course):
                continue

            for group_id in self._project_group_ids_for_course(code, course):
                project_instructors = self._project_instructors_for_course(course)
                if not project_instructors:
                    self.unscheduled_reasons.append(
                        f"No instructor assigned for project course {code}"
                    )
                    continue

                base_day, slot = self._project_day_and_slot(course)
                explicit_day = bool(course.get("dayOfWeek") or course.get("day"))

                for index, instructor in enumerate(project_instructors):
                    day = (
                        base_day
                        if explicit_day
                        else self.days[index % max(1, len(self.days))]
                    )
                    component = (
                        "LECTURE"
                        if instructor.get("instructorType") == "DOCTOR"
                        else "SECTION"
                    )
                    candidate = {
                        "sessionType": component,
                        "courseCode": code,
                        "isOnline": True,
                        "isProject": True,
                    }

                    if self._has_group_time_conflict(group_id, day, slot, candidate):
                        self.unscheduled_reasons.append(
                            f"Project time conflict for {code} instructor={instructor.get('instructorId')} group={group_id} slot={day} {slot}"
                        )
                        continue

                    session = self._create_project_session(
                        code,
                        course,
                        group_id,
                        day,
                        slot,
                        component,
                        instructor,
                    )
                    if session.get("sectionId"):
                        section_ids = self.group_details[group_id].setdefault("sectionIds", [])
                        if session["sectionId"] not in section_ids:
                            section_ids.append(session["sectionId"])
                    self._place_session(group_id, session)

    def _schedule_arabic_online_courses(self) -> None:
        arabic_courses = [
            (code, course)
            for code, course in self.courses.items()
            if course.get("isArabicOnline") is True
        ]

        for course_index, (code, course) in enumerate(arabic_courses):
            group_ids = self._ensure_arabic_online_group_for_course(code, course)

            for group_id in group_ids:
                day, slot = self._arabic_day_and_slot(course, course_index)
                session = self._create_arabic_online_session(
                    code, course, group_id, day, slot
                )
                self._place_session(group_id, session, reserve_resources=False)

    def _create_arabic_online_session(
        self,
        code: str,
        course: dict,
        group_id: str,
        day: str,
        slot: str,
    ) -> dict:
        self.session_counter += 1
        instructor = self._arabic_instructor_for_course(course)

        session = {
            "sessionId": f"SESSION_{self.session_counter:06d}",
            "sessionType": "LECTURE",
            "courseCode": code,
            "courseName": course.get("courseName", code),
            "courseNameAr": course.get("courseNameAr"),
            "groupId": group_id,
            "sectionId": None,
            "instructorId": instructor.get("instructorId") if instructor else None,
            "instructorName": (
                course.get("doctorName")
                or course.get("instructorName")
                or (instructor.get("name") if instructor else None)
            ),
            "roomId": None,
            "roomNumber": None,
            "roomType": None,
            "dayOfWeek": day,
            "timeSlot": slot,
            "studentCount": self.group_sizes.get(group_id, 0),
            "totalStudentCount": self.group_sizes.get(group_id, 0),
            "isOnline": True,
            "isRecordedOnline": True,
            "isArabicOnline": True,
        }

        return self._merge_passthrough_course_fields(session, course)

    def _create_project_session(
        self,
        code: str,
        course: dict,
        group_id: str,
        day: str,
        slot: str,
        component: str = "LECTURE",
        instructor: Optional[dict] = None,
    ) -> dict:
        self.session_counter += 1
        details = self._project_details(course)
        component = str(component or "LECTURE").strip().upper()
        is_section = component == "SECTION"
        level = self._safe_int(
            self.group_details.get(group_id, {}).get("level"),
            self._project_levels(course)[0],
        )
        instructor_id = (
            instructor.get("instructorId")
            if instructor
            else details.get("assistantId") if is_section else details.get("doctorId")
        )
        instructor_name = (
            instructor.get("name")
            if instructor
            else details.get("assistantName") if is_section else details.get("doctorName")
        )
        section_id = None
        if is_section:
            section_suffix = instructor_id if instructor_id is not None else "PROJECT"
            section_id = f"{code}-{group_id}-PROJECT-SECTION-{section_suffix}"

        session = {
            "sessionId": f"SESSION_{self.session_counter:06d}",
            "sessionType": "SECTION" if is_section else "LECTURE",
            "projectComponent": component,
            "courseCode": code,
            "courseName": course.get("courseName", code),
            "courseNameAr": course.get("courseNameAr"),
            "groupId": group_id,
            "sectionId": section_id,
            "instructorId": instructor_id,
            "instructorName": instructor_name,
            "doctorName": instructor_name if not is_section else details.get("doctorName"),
            "assistantName": instructor_name if is_section else details.get("assistantName"),
            "roomId": None,
            "roomNumber": "ONLINE",
            "roomType": "ONLINE",
            "lectureRoomNumber": details.get("lectureRoomNumber"),
            "sectionRoomNumber": details.get("sectionRoomNumber"),
            "dayOfWeek": day,
            "timeSlot": slot,
            "studentCount": self.group_sizes.get(group_id, 0),
            "isOnline": True,
            "isRecordedOnline": False,
            "isProject": True,
            "level": level,
            "academicLevel": level,
            "levels": [level],
        }

        return self._merge_passthrough_course_fields(session, course)

    def _create_level_groups(self) -> None:
        if (
            self.input_data.get("useProvidedStudentGroups") is True
            and self._create_student_groups_from_input()
        ):
            return

        generated = self._create_student_groups_from_courses()
        if generated:
            return

        level_max = defaultdict(int)

        for course in self.courses.values():
            if (
                self._is_online_course(course)
                or self._is_display_only_course(course)
                or self._is_project_course(course)
            ):
                continue

            level = self._course_level(course)
            enrollment = self._safe_int(course.get("enrollmentCount"), 0)
            level_max[level] = max(level_max[level], enrollment)

        for level in sorted(level_max):
            max_enrollment = level_max[level]

            if max_enrollment <= 0:
                continue

            group_count = max(1, math.ceil(max_enrollment / self.max_lecture_group_size))
            sizes = self._split_evenly(max_enrollment, group_count)

            for index, size in enumerate(sizes, start=1):
                group_id = self._generated_group_id(level, index)

                self.group_sizes[group_id] = size
                self.group_details[group_id] = {
                    "groupId": group_id,
                    "level": level,
                    "studentCount": size,
                    "department": None,
                    "departments": [],
                    "courseCodes": [
                        code
                        for code, course in self.courses.items()
                        if (
                            self._course_level(course) == level
                            and not self._is_online_course(course)
                            and not self._is_display_only_course(course)
                            and not self._is_project_course(course)
                        )
                    ],
                }

    def _create_project_groups(self) -> None:
        for code, course in sorted(self.courses.items()):
            if not self._is_project_course(course):
                continue

            for level in self._project_levels(course):
                group_id = self._project_group_id(level, code)
                if group_id in self.group_details:
                    continue

                departments = self._normalize_departments(course.get("departments"))
                total = self._project_student_count(course, level)

                self.group_sizes[group_id] = total
                self.group_details[group_id] = {
                    "groupId": group_id,
                    "level": level,
                    "studentCount": total,
                    "department": None,
                    "departments": departments if level > 2 else [],
                    "courseCodes": [code],
                    "isProjectGroup": True,
                }

    def _build_demands(self) -> Tuple[List[dict], List[dict], List[dict]]:
        lectures: List[dict] = []
        sections: List[dict] = []
        online: List[dict] = []

        for code, course in self.courses.items():
            if (
                code in self.blocked_courses
                or self._is_display_only_course(course)
                or course.get("isArabicOnline") is True
                or self._is_project_course(course)
            ):
                continue

            is_online = self._is_online_course(course)
            group_ids = self._target_group_ids_for_course(code, course)

            if not is_online and course.get("labType") is not None and group_ids:
                available_sections = self._available_section_placements_count(code, course)
                if available_sections <= 0:
                    self.warnings.append(
                        f"No section placements available for {code}; lectures will be scheduled without sections."
                    )

            for group_id in group_ids:
                group_size = self._course_group_size(code, group_id)

                lecture_demand = {
                    "kind": "ONLINE_LECTURE" if is_online else "LECTURE",
                    "sessionType": "LECTURE",
                    "courseCode": code,
                    "courseName": course.get("courseName", code),
                    "groupId": group_id,
                    "studentCount": group_size,
                    "sectionId": None,
                    "isOnline": is_online,
                    "isArabicOnline": course.get("isArabicOnline") is True,
                    "labType": None,
                    "difficulty": self._course_difficulty(course, is_online),
                }

                if is_online:
                    online.append(lecture_demand)
                else:
                    lectures.append(lecture_demand)

                if not is_online and course.get("labType") is not None:
                    lab_type = self._normalized_lab_type(course.get("labType"))
                    section_count = max(
                        self._target_sections_count(group_size),
                        max(1, len(self.group_details.get(group_id, {}).get("sectionIds") or [])),
                    )

                    if section_count <= 0:
                        continue

                    sections.append({
                        "kind": "SECTION_BUNDLE",
                        "courseCode": code,
                        "courseName": course.get("courseName", code),
                        "groupId": group_id,
                        "groupSize": group_size,
                        "targetSections": section_count,
                        "minSections": section_count,
                        "labType": lab_type,
                        "difficulty": self._section_difficulty(course),
                    })

        return lectures, sections, online

    def _schedule_single_session(self, demand: dict) -> bool:
        course_code = demand["courseCode"]
        group_id = demand["groupId"]
        is_online = demand["isOnline"]

        instructors = self._get_matching_instructors(course_code, "LECTURE")
        rooms = self._get_matching_rooms("LECTURE", None, demand["studentCount"], is_online)
        if not is_online and not rooms:
            rooms = self._get_lecture_room_candidates(
                demand["studentCount"],
                allow_capacity_overflow=True,
            )
        elif not is_online:
            rooms = self._get_lecture_room_candidates(
                demand["studentCount"],
                allow_capacity_overflow=True,
            )

        if not instructors and not demand.get("isArabicOnline"):
            return self._add_unscheduled(
                demand,
                f"No doctor/instructor for {course_code} lecture group={group_id}",
            )

        if not is_online and not rooms:
            return self._add_unscheduled(
                demand,
                f"No suitable lecture room for {course_code} group={group_id} studentCount={demand['studentCount']}",
            )

        slots = (
            self._online_slots_for_course(course_code)
            if is_online
            else self._preferred_slots_for_course(course_code, "LECTURE")
        )

        for day in self._preferred_days_for_group(group_id):
            for slot in self._preferred_slots_for_group_on_day(group_id, day, slots):
                if self._has_group_time_conflict(group_id, day, slot, demand):
                    continue

                candidate_instructors = (
                    self._least_busy_instructors_for_course(instructors, course_code)
                    if instructors
                    else [None]
                )

                for instructor in candidate_instructors:
                    if instructor and not self._can_use_instructor(instructor, day, slot, demand):
                        continue

                    if is_online:
                        session = self._create_scheduled_session(
                            demand, instructor, None, day, slot
                        )
                        self._place_session(group_id, session)
                        return True

        for instructor, room, day, slot in self._lecture_placement_candidates(
            demand,
            instructors,
            rooms,
            slots,
        ):
            if self._safe_int(room.get("capacity"), 0) < demand["studentCount"]:
                self.warnings.append(
                    f"Used largest available room for {course_code} "
                    f"group={group_id} although studentCount={demand['studentCount']} "
                    f"exceeds roomCapacity={self._safe_int(room.get('capacity'), 0)}."
                )

            session = self._create_scheduled_session(
                demand, instructor, room, day, slot
            )
            self._place_session(group_id, session)
            return True

        return False

    def _lecture_placement_candidates(
        self,
        demand: dict,
        instructors: List[dict],
        rooms: List[dict],
        slots: List[str],
    ) -> List[Tuple[dict, dict, str, str]]:
        group_id = demand["groupId"]
        course_code = demand["courseCode"]
        day_order = {day: index for index, day in enumerate(self.days)}
        slot_order = {slot: index for index, slot in enumerate(slots)}
        candidates = []

        for instructor in instructors:
            if not instructor:
                continue

            instructor_id = instructor["instructorId"]
            course_lecture_count = sum(
                1
                for session in self.instructor_schedules.get(instructor_id, [])
                if session.get("courseCode") == course_code
                and session.get("sessionType") == "LECTURE"
            )
            course_slot_share = self._instructor_course_lecture_slot_share(
                instructor,
                course_code,
            )
            over_preferred_share = (
                course_slot_share <= 0
                or course_lecture_count >= course_slot_share
            )

            instructor_total_count = len(self.instructor_schedules.get(instructor_id, []))

            for day in self._preferred_days_for_group(group_id):
                for slot in self._preferred_slots_for_group_on_day(group_id, day, slots):
                    if self._has_group_time_conflict(group_id, day, slot, demand):
                        continue

                    if not self._can_use_instructor(instructor, day, slot, demand):
                        continue

                    for room in self._best_lecture_rooms(rooms):
                        if not self._can_use_room(room, day, slot):
                            continue

                        candidates.append((
                            (
                                1 if over_preferred_share else 0,
                                course_lecture_count,
                                instructor_total_count,
                                day_order.get(day, 999),
                                slot_order.get(slot, 999),
                                instructor_id,
                                -self._safe_int(room.get("capacity"), 0),
                                room["roomId"],
                            ),
                            instructor,
                            room,
                            day,
                            slot,
                        ))

                        break

        return [
            (instructor, room, day, slot)
            for _, instructor, room, day, slot in sorted(candidates, key=lambda item: item[0])
        ]

    def _schedule_section_bundle(self, demand: dict) -> bool:
        course_code = demand["courseCode"]
        group_id = demand["groupId"]

        section_sizes = self._distribute_group_to_sections(
            demand["groupSize"],
            demand["targetSections"],
            self.max_section_size,
        )

        if not section_sizes:
            return self._add_unscheduled(
                demand,
                f"Section capacity is not enough for {course_code} group={group_id}",
            )

        instructors = self._get_matching_instructors(course_code, "SECTION")
        rooms = self._get_matching_rooms("SECTION", demand["labType"], 1, False)

        if not instructors:
            return self._add_unscheduled(
                demand,
                f"No TA/instructor for {course_code} sections group={group_id}",
            )

        if not rooms:
            return self._add_unscheduled(
                demand,
                f"No suitable rooms for {course_code} sections group={group_id} labType={demand['labType']}",
            )

        scheduled = 0
        checkpoint = self._state_checkpoint()

        for index, section_size in enumerate(section_sizes, start=1):
            section_id = self._section_label(group_id, index)

            section_demand = {
                "kind": "SECTION",
                "sessionType": "SECTION",
                "courseCode": course_code,
                "courseName": demand["courseName"],
                "groupId": group_id,
                "studentCount": section_size,
                "sectionId": section_id,
                "isOnline": False,
                "labType": demand["labType"],
            }

            if self._schedule_one_section(section_demand, instructors, rooms):
                scheduled += 1

        if scheduled <= 0:
            fallback_rooms = []
            if demand.get("labType") == "LAB_ONLY":
                fallback_rooms = self._get_matching_rooms("SECTION", "GENERAL_LAB", 1, False)

            if fallback_rooms:
                self._restore_state(checkpoint)
                scheduled = 0

                for index, section_size in enumerate(section_sizes, start=1):
                    section_id = self._section_label(group_id, index)

                    section_demand = {
                        "kind": "SECTION",
                        "sessionType": "SECTION",
                        "courseCode": course_code,
                        "courseName": demand["courseName"],
                        "groupId": group_id,
                        "studentCount": section_size,
                        "sectionId": section_id,
                        "isOnline": False,
                        "labType": "GENERAL_LAB",
                    }

                    if self._schedule_one_section(section_demand, instructors, fallback_rooms):
                        scheduled += 1

                if scheduled > 0:
                    self.warnings.append(
                        f"Used a general room fallback for {course_code} sections group={group_id} because lab rooms were not enough."
                    )

                    if scheduled != len(section_sizes):
                        self.warnings.append(
                            self._diagnose_partial_sections(
                                demand,
                                scheduled,
                                len(section_sizes),
                                max(1, demand.get("minSections", 1)),
                            )
                        )

                    return True

            self._restore_state(checkpoint)
            return self._add_unscheduled(
                demand,
                self._diagnose_partial_sections(
                    demand,
                    scheduled,
                    len(section_sizes),
                    1,
                ),
            )

        if scheduled != len(section_sizes):
            self.warnings.append(
                self._diagnose_partial_sections(
                    demand,
                    scheduled,
                    len(section_sizes),
                    max(1, demand.get("minSections", 1)),
                )
            )

        return True

    def _schedule_one_section(
        self,
        demand: dict,
        instructors: List[dict],
        rooms: List[dict],
    ) -> bool:
        group_id = demand["groupId"]
        section_id = demand["sectionId"]

        slots = self._preferred_slots_for_course(demand["courseCode"], "SECTION")
        day_order = {day: index for index, day in enumerate(self.days)}
        slot_order = {slot: index for index, slot in enumerate(slots)}
        candidates = []

        for day in self._preferred_days_for_group(group_id):
            for slot in self._preferred_slots_for_group_on_day(group_id, day, slots):
                if self._has_group_time_conflict(group_id, day, slot, demand):
                    continue

                if any(
                    busy_section == section_id
                    and busy_day == day
                    and self._slots_overlap(busy_slot, slot)
                    for busy_section, busy_day, busy_slot in self.section_busy
                ):
                    continue

                for instructor in self._least_busy_instructors(instructors):
                    if not self._can_use_instructor(instructor, day, slot, demand):
                        continue

                    for room in self._least_busy_rooms(rooms):
                        if self._safe_int(room.get("capacity"), 0) < demand["studentCount"]:
                            continue

                        if self._can_use_room(room, day, slot):
                            general_section_room_priority = (
                                0
                                if (
                                    demand.get("labType") == "GENERAL_LAB"
                                    and room.get("roomType") == "GENERAL"
                                )
                                else 1
                            )
                            candidates.append((
                                (
                                    general_section_room_priority,
                                    len(self.room_schedules.get(room.get("roomId"), [])),
                                    len(self.instructor_schedules.get(instructor.get("instructorId"), [])),
                                    day_order.get(day, 999),
                                    slot_order.get(slot, 999),
                                    room.get("roomId") or 0,
                                    instructor.get("instructorId") or 0,
                                ),
                                instructor,
                                room,
                                day,
                                slot,
                            ))

        if not candidates:
            return False

        _, instructor, room, day, slot = min(candidates, key=lambda item: item[0])
        session = self._create_scheduled_session(demand, instructor, room, day, slot)
        self._place_session(group_id, session)
        return True


    def _get_matching_instructors(self, course_code: str, session_type: str) -> List[dict]:
        course = self.courses.get(course_code, {})
        course_instructor_ids = set(course.get("instructorIds") or [])
        assigned = [
            instructor
            for instructor in self.instructors.values()
            if self._instructor_matches_course_category(instructor, course)
            and (
                course_code in self._assigned_course_codes(instructor)
                or instructor.get("instructorId") in course_instructor_ids
            )
        ]

        if session_type == "LECTURE":
            doctors = [
                instructor
                for instructor in assigned
                if instructor.get("instructorType") == "DOCTOR"
            ]
            if doctors:
                return doctors

            return assigned

        return [
            instructor
            for instructor in assigned
            if instructor.get("instructorType") == "TA"
        ]

    def _get_matching_rooms(
        self,
        session_type: str,
        lab_type: Optional[str],
        student_count: int,
        is_online: bool,
    ) -> List[dict]:
        if is_online:
            return []

        rooms = list(self.rooms.values())

        if session_type == "LECTURE":
            return [
                room
                for room in rooms
                if room.get("roomType") == "GENERAL"
                and self._safe_int(room.get("capacity"), 0) >= max(1, student_count)
            ]

        elif lab_type == "LAB_ONLY":
            candidates = [
                room
                for room in rooms
                if room.get("roomType") == "LAB_ONLY"
            ]

        elif lab_type in {"PH101_LAB", "PH101_LA"}:
            candidates = [
                room
                for room in rooms
                if room.get("roomType") in {"PH101_LAB", "PH101_LA"}
            ]

        else:
            candidates = [
                room
                for room in rooms
                if room.get("roomType") in {"GENERAL", "LAB_ONLY"}
            ]
            candidates = self._general_section_room_order(candidates)

        return [
            room
            for room in candidates
            if self._safe_int(room.get("capacity"), 0) >= max(1, student_count)
        ]

    def _general_section_room_order(self, rooms: List[dict]) -> List[dict]:
        return sorted(
            rooms,
            key=lambda room: (
                0 if room.get("roomType") == "GENERAL" else 1,
                len(self.room_schedules.get(room.get("roomId"), [])),
                -self._safe_int(room.get("capacity"), 0),
                room.get("roomId") or 0,
            ),
        )

    def _get_lecture_room_candidates(
        self,
        student_count: int,
        allow_capacity_overflow: bool = False,
    ) -> List[dict]:
        rooms = [
            room
            for room in self.rooms.values()
            if room.get("roomType") == "GENERAL"
        ]
        suitable = [
            room
            for room in rooms
            if self._safe_int(room.get("capacity"), 0) >= max(1, student_count)
        ]

        if not allow_capacity_overflow:
            return suitable

        suitable_ids = {room["roomId"] for room in suitable}
        overflow = [room for room in rooms if room["roomId"] not in suitable_ids]
        return suitable + overflow

    def _course_lecture_group_capacity(self, course: dict) -> int:
        explicit = self._safe_int(
            course.get("maxLectureGroupSize")
            or course.get("lectureGroupCapacity")
            or course.get("lectureCapacity"),
            None,
        )
        if explicit is not None and explicit > 0:
            return explicit

        if self.explicit_max_lecture_group_size:
            return self.explicit_max_lecture_group_size

        return max(1, self.max_lecture_group_size)

    def _largest_general_room_capacity(self) -> int:
        capacities = [
            self._safe_int(room.get("capacity"), 0)
            for room in self.rooms.values()
            if room.get("roomType") == "GENERAL"
        ]
        if capacities:
            return max(1, max(capacities))

        return max(1, self.max_lecture_group_size)

    def _course_lecture_group_count(self, course: dict, student_count: int) -> int:
        capacity = self._course_lecture_group_capacity(course)
        largest_room_capacity = self._largest_general_room_capacity()
        flexible_single_group_limit = int(math.ceil(capacity * 1.35))

        if (
            student_count <= largest_room_capacity
            and student_count <= flexible_single_group_limit
        ):
            return 1

        return max(1, math.ceil(max(1, student_count) / max(1, capacity)))

    def _course_lecture_instructor_slot_count(self, course: dict) -> int:
        course_code = self._course_code(course)
        if not course_code:
            return 0

        instructors = self._get_matching_instructors(course_code, "LECTURE")
        if not instructors:
            return 0

        return sum(
            self._instructor_course_lecture_slot_share(instructor, course_code)
            for instructor in instructors
        )

    def _instructor_regular_lecture_slot_count(
        self,
        instructor: dict,
        course_code: str,
    ) -> int:
        slots = self._preferred_slots_for_course(course_code, "LECTURE")
        return sum(
            1
            for day in self.days
            for slot in slots
            if self._is_instructor_available(instructor, day, slot)
        )

    def _instructor_course_lecture_slot_share(
        self,
        instructor: dict,
        course_code: str,
    ) -> int:
        shared_courses = self._schedulable_lecture_courses_for_instructor(instructor)
        if course_code not in shared_courses:
            return 0

        slot_count = self._instructor_regular_lecture_slot_count(instructor, course_code)
        if slot_count <= 0:
            return 0

        allocation = {code: 0 for code in shared_courses}
        remaining = slot_count
        essential_needs = {}

        for code in shared_courses:
            desired = self._course_desired_lecture_count(code)
            other_doctor_slots = self._other_doctor_lecture_slot_count(
                instructor,
                code,
            )
            essential_needs[code] = max(0, desired - other_doctor_slots)

        for code, essential in sorted(
            essential_needs.items(),
            key=lambda item: (
                -item[1],
                -self._course_relevant_student_count(self.courses.get(item[0], {})),
                item[0],
            ),
        ):
            if remaining <= 0:
                break

            assigned = min(essential, remaining)
            allocation[code] += assigned
            remaining -= assigned

        if remaining <= 0:
            return allocation.get(course_code, 0)

        caps = {
            code: max(0, self._course_resource_lecture_cap(code) - allocation[code])
            for code in shared_courses
        }
        eligible_codes = [code for code, cap in caps.items() if cap > 0]
        if not eligible_codes:
            return allocation.get(course_code, 0)

        weights = {
            code: max(
                1,
                self._course_resource_lecture_cap(code),
                self._course_relevant_student_count(self.courses.get(code, {})),
            )
            for code in eligible_codes
        }
        weight_total = sum(weights.values())
        shares = []
        assigned_extra = 0

        for code in eligible_codes:
            exact = remaining * weights[code] / max(1, weight_total)
            extra = min(caps[code], int(math.floor(exact)))
            allocation[code] += extra
            assigned_extra += extra
            shares.append((
                exact - extra,
                self._course_relevant_student_count(self.courses.get(code, {})),
                code,
            ))

        for _, _, code in sorted(shares, reverse=True):
            if assigned_extra >= remaining:
                break
            if allocation[code] >= self._course_resource_lecture_cap(code):
                continue

            allocation[code] += 1
            assigned_extra += 1

        return allocation.get(course_code, 0)

    def _other_doctor_lecture_slot_count(
        self,
        current_instructor: dict,
        course_code: str,
    ) -> int:
        current_id = current_instructor.get("instructorId")
        count = 0

        for instructor in self._get_matching_instructors(course_code, "LECTURE"):
            if instructor.get("instructorId") == current_id:
                continue

            count += self._instructor_regular_lecture_slot_count(instructor, course_code)

        return count

    def _course_relevant_student_count(self, course: dict) -> int:
        return sum(self._course_level_student_counts(course).values())

    def _course_desired_lecture_count(self, course_code: str) -> int:
        course = self.courses.get(course_code, {})
        relevant_students = self._course_relevant_student_count(course)
        if relevant_students <= 0:
            return 0

        return self._course_lecture_group_count(course, relevant_students)

    def _course_resource_lecture_cap(self, course_code: str) -> int:
        course = self.courses.get(course_code, {})
        relevant_students = self._course_relevant_student_count(course)
        if relevant_students <= 0:
            return 0

        by_size = max(
            self._course_desired_lecture_count(course_code),
            relevant_students // max(1, self.min_lecture_group_size),
        )

        return max(1, by_size)

    def _schedulable_lecture_courses_for_instructor(self, instructor: dict) -> List[str]:
        instructor_id = instructor.get("instructorId")
        assigned_codes = self._assigned_course_codes(instructor)
        result = []

        for code, course in self.courses.items():
            if (
                code in self.blocked_courses
                or self._is_online_course(course)
                or self._is_display_only_course(course)
                or self._is_project_course(course)
                or self._course_total_student_count(course) <= 0
            ):
                continue

            course_instructor_ids = set(course.get("instructorIds") or [])
            if code not in assigned_codes and instructor_id not in course_instructor_ids:
                continue

            if not self._instructor_matches_course_category(instructor, course):
                continue

            result.append(code)

        return result

    def _allocate_course_group_counts_by_level(
        self,
        course: dict,
        level_counts: Dict[int, int],
    ) -> Dict[int, int]:
        cleaned_counts = {
            level: self._safe_int(count, 0)
            for level, count in (level_counts or {}).items()
            if self._safe_int(count, 0) > 0
        }
        if not cleaned_counts:
            return {}

        target_capacity = self._course_lecture_group_capacity(course)
        room_capacity = self._largest_general_room_capacity()
        total_students = sum(cleaned_counts.values())
        target_group_count = max(
            1,
            math.ceil(total_students / max(1, target_capacity)),
        )
        room_min_group_count = max(
            1,
            math.ceil(total_students / max(1, room_capacity)),
        )
        instructor_slot_count = self._course_lecture_instructor_slot_count(course)

        total_group_count = target_group_count
        if (
            instructor_slot_count > 0
            and instructor_slot_count < target_group_count
            and instructor_slot_count >= room_min_group_count
        ):
            total_group_count = instructor_slot_count

        if len(cleaned_counts) > 1 and total_students <= room_capacity and total_group_count == 1:
            primary_level = max(cleaned_counts, key=lambda level: (cleaned_counts[level], level))
            return {primary_level: 1}

        per_level_min = {
            level: max(1, math.ceil(count / max(1, room_capacity)))
            for level, count in cleaned_counts.items()
        }
        per_level_target = {
            level: max(1, math.ceil(count / max(1, target_capacity)))
            for level, count in cleaned_counts.items()
        }
        per_level_resource = {
            level: max(
                per_level_target[level],
                self._safe_int(count, 0) // max(1, self.min_lecture_group_size),
            )
            for level, count in cleaned_counts.items()
        }
        resource_group_cap = max(1, sum(per_level_resource.values()))

        if instructor_slot_count > total_group_count:
            total_group_count = min(instructor_slot_count, resource_group_cap)

        if len(cleaned_counts) == 1:
            level, _count = next(iter(cleaned_counts.items()))
            return {level: max(1, total_group_count)}

        if sum(per_level_min.values()) > total_group_count:
            return per_level_target

        allocation = dict(per_level_min)
        remaining = total_group_count - sum(allocation.values())
        if remaining <= 0:
            return allocation

        candidates = []
        for level, count in cleaned_counts.items():
            room_groups = allocation[level]
            target_groups = per_level_resource[level]
            if room_groups >= target_groups:
                continue

            pressure = count / max(1, room_groups)
            candidates.append((pressure, count, level))

        for _, _, level in sorted(candidates, reverse=True):
            while remaining > 0 and allocation[level] < per_level_resource[level]:
                allocation[level] += 1
                remaining -= 1

        return allocation

    def _can_use_instructor(
        self,
        instructor: dict,
        day: str,
        slot: str,
        demand: dict,
    ) -> bool:
        if demand.get("isOnline") and demand["courseCode"] in self.online_recorded_courses:
            return True

        instructor_id = instructor["instructorId"]

        return (
            self._is_instructor_available(instructor, day, slot)
            and not self._has_instructor_time_conflict(instructor_id, day, slot)
        )

    def _can_use_room(self, room: dict, day: str, slot: str) -> bool:
        return not self._has_room_time_conflict(room["roomId"], day, slot)

    def _diagnose_unscheduled_demand(self, demand: dict) -> str:
        course_code = demand["courseCode"]
        group_id = demand["groupId"]
        is_online = demand.get("isOnline") is True

        if demand["sessionType"] == "LECTURE":
            instructors = self._get_matching_instructors(course_code, "LECTURE")
            rooms = (
                []
                if is_online
                else self._get_lecture_room_candidates(
                    demand["studentCount"],
                    allow_capacity_overflow=True,
                )
            )

            if not instructors and not demand.get("isArabicOnline"):
                return f"No doctor/instructor for {course_code} lecture group={group_id}"

            if not is_online and not rooms:
                return f"No suitable lecture room for {course_code} group={group_id} studentCount={demand['studentCount']}"

            slots = (
                self._online_slots_for_course(course_code)
                if is_online
                else self._preferred_slots_for_course(course_code, "LECTURE")
            )
            if self._all_candidate_slots_have_group_conflict(group_id, slots, demand):
                return f"No free group slot for {course_code} lecture group={group_id}"

            if instructors and not self._has_any_instructor_slot(instructors, group_id, slots, demand):
                return f"Doctor/instructor availability is not enough for {course_code} lecture group={group_id}"

            if not is_online and rooms and not self._has_any_room_slot(rooms, group_id, slots, demand):
                return f"Lecture rooms are not enough for {course_code} group={group_id}"

            return f"Could not schedule lecture for {course_code} group={group_id}; combined constraints are too tight"

        if demand["sessionType"] == "SECTION":
            instructors = self._get_matching_instructors(course_code, "SECTION")
            rooms = self._get_matching_rooms("SECTION", demand.get("labType"), demand["studentCount"], False)

            if not instructors:
                return f"No TA/instructor for {course_code} section group={group_id}"

            if not rooms:
                return f"No suitable lab rooms for {course_code} section group={group_id} labType={demand.get('labType')}"

            slots = self._preferred_slots_for_course(course_code, "SECTION")
            if self._all_candidate_slots_have_group_conflict(group_id, slots, demand):
                return f"No free group slot for {course_code} section group={group_id}"

            if not self._has_any_instructor_slot(instructors, group_id, slots, demand):
                return f"TA/instructor availability is not enough for {course_code} section group={group_id}"

            if not self._has_any_room_slot(rooms, group_id, slots, demand):
                return f"Lab rooms are not enough for {course_code} section group={group_id} labType={demand.get('labType')}"

        return f"Could not schedule {demand['kind']} for {course_code} group={group_id}"

    def _diagnose_partial_sections(
        self,
        demand: dict,
        scheduled: int,
        target: int,
        minimum: int,
    ) -> str:
        course_code = demand["courseCode"]
        group_id = demand["groupId"]
        instructors = self._get_matching_instructors(course_code, "SECTION")
        rooms = self._get_matching_rooms("SECTION", demand.get("labType"), 1, False)

        if not instructors:
            cause = "No TA/instructor"
        elif not rooms:
            cause = f"No suitable lab rooms labType={demand.get('labType')}"
        else:
            slots = self._preferred_slots_for_course(course_code, "SECTION")
            if self._all_candidate_slots_have_group_conflict(group_id, slots, demand):
                cause = "No free group slots"
            elif not self._has_any_instructor_slot(instructors, group_id, slots, demand):
                cause = "TA/instructor availability is not enough"
            elif not self._has_any_room_slot(rooms, group_id, slots, demand):
                cause = f"Lab rooms are not enough labType={demand.get('labType')}"
            else:
                cause = "Combined constraints are too tight"

        return (
            f"Only {scheduled} sections scheduled for {course_code} group={group_id}; "
            f"minimum={minimum}, target={target}. Cause: {cause}"
        )

    def _all_candidate_slots_have_group_conflict(
        self,
        group_id: str,
        slots: List[str],
        demand: Optional[dict] = None,
    ) -> bool:
        for day in self._preferred_days_for_group(group_id):
            for slot in slots:
                if not self._has_group_time_conflict(group_id, day, slot, demand):
                    return False

        return True

    def _has_any_instructor_slot(
        self,
        instructors: List[dict],
        group_id: str,
        slots: List[str],
        demand: dict,
    ) -> bool:
        for day in self._preferred_days_for_group(group_id):
            for slot in slots:
                if self._has_group_time_conflict(group_id, day, slot, demand):
                    continue

                for instructor in instructors:
                    if self._can_use_instructor(instructor, day, slot, demand):
                        return True

        return False

    def _has_any_room_slot(
        self,
        rooms: List[dict],
        group_id: str,
        slots: List[str],
        demand: Optional[dict] = None,
    ) -> bool:
        for day in self._preferred_days_for_group(group_id):
            for slot in slots:
                if self._has_group_time_conflict(group_id, day, slot, demand):
                    continue

                for room in rooms:
                    if self._can_use_room(room, day, slot):
                        return True

        return False

    def _available_lecture_placements_count(self, course_code: str, course: dict) -> int:
        instructors = self._get_matching_instructors(course_code, "LECTURE")
        rooms = self._get_matching_rooms(
            "LECTURE",
            None,
            1,
            False,
        )

        return self._count_free_instructor_room_slots(
            instructors,
            rooms,
            self._preferred_slots_for_course(course_code, "LECTURE"),
            {
                "sessionType": "LECTURE",
                "courseCode": course_code,
                "isOnline": False,
            },
        )

    def _lecture_resource_shortage_reason(self, course_code: str, course: dict) -> str:
        instructors = self._get_matching_instructors(course_code, "LECTURE")
        rooms = self._get_matching_rooms("LECTURE", None, 1, False)

        if not instructors:
            return f"No doctor assigned for {course_code} lectures."

        if not rooms:
            return f"No lecture rooms available for {course_code}."

        slots = self._preferred_slots_for_course(course_code, "LECTURE")
        has_doctor_time = any(
            self._can_use_instructor(
                instructor,
                day,
                slot,
                {
                    "sessionType": "LECTURE",
                    "courseCode": course_code,
                    "isOnline": False,
                },
            )
            for day in self.days
            for slot in slots
            for instructor in instructors
        )

        if not has_doctor_time:
            return f"No valid doctor availability found for {course_code} lectures."

        has_room_time = any(
            self._can_use_room(room, day, slot)
            for day in self.days
            for slot in slots
            for room in rooms
        )

        if not has_room_time:
            return f"Lecture rooms are not available in the valid time slots for {course_code}."

        return f"No combined doctor+lecture-room placement is available for {course_code}; add a room in one of the valid doctor slots."

    def _reserve_precheck_lecture_placements(
        self,
        course_code: str,
        course: dict,
        needed: int,
        shadow_instructor_busy: set,
        shadow_room_busy: set,
    ) -> int:
        instructors = self._get_matching_instructors(course_code, "LECTURE")
        rooms = self._get_matching_rooms(
            "LECTURE",
            None,
            1,
            False,
        )

        return self._reserve_precheck_placements(
            instructors,
            rooms,
            self._preferred_slots_for_course(course_code, "LECTURE"),
            {
                "sessionType": "LECTURE",
                "courseCode": course_code,
                "isOnline": False,
            },
            needed,
            shadow_instructor_busy,
            shadow_room_busy,
        )

    def _available_section_placements_count(self, course_code: str, course: dict) -> int:
        lab_type = self._normalized_lab_type(course.get("labType"))
        instructors = self._get_matching_instructors(course_code, "SECTION")
        rooms = self._get_matching_rooms("SECTION", lab_type, 1, False)

        return self._count_free_instructor_room_slots(
            instructors,
            rooms,
            self._preferred_slots_for_course(course_code, "SECTION"),
            {
                "sessionType": "SECTION",
                "courseCode": course_code,
                "isOnline": False,
                "labType": lab_type,
            },
        )

    def _reserve_precheck_section_placements(
        self,
        course_code: str,
        course: dict,
        needed: int,
        shadow_instructor_busy: set,
        shadow_room_busy: set,
    ) -> int:
        lab_type = self._normalized_lab_type(course.get("labType"))
        instructors = self._get_matching_instructors(course_code, "SECTION")
        rooms = self._get_matching_rooms("SECTION", lab_type, 1, False)

        return self._reserve_precheck_placements(
            instructors,
            rooms,
            self._preferred_slots_for_course(course_code, "SECTION"),
            {
                "sessionType": "SECTION",
                "courseCode": course_code,
                "isOnline": False,
                "labType": lab_type,
            },
            needed,
            shadow_instructor_busy,
            shadow_room_busy,
        )

    def _reserve_precheck_placements(
        self,
        instructors: List[dict],
        rooms: List[dict],
        slots: List[str],
        demand: dict,
        needed: int,
        shadow_instructor_busy: set,
        shadow_room_busy: set,
    ) -> int:
        if not instructors or not rooms or needed <= 0:
            return 0

        reserved = 0
        for day in self.days:
            for slot in slots:
                for instructor in self._least_busy_instructors(instructors):
                    instructor_id = instructor["instructorId"]
                    if (instructor_id, day, slot) in shadow_instructor_busy:
                        continue

                    if not self._can_use_instructor(instructor, day, slot, demand):
                        continue

                    for room in self._least_busy_rooms(rooms):
                        room_id = room["roomId"]
                        if (room_id, day, slot) in shadow_room_busy:
                            continue

                        if not self._can_use_room(room, day, slot):
                            continue

                        shadow_instructor_busy.add((instructor_id, day, slot))
                        shadow_room_busy.add((room_id, day, slot))
                        reserved += 1

                        if reserved >= needed:
                            return reserved

                        break

        return reserved

    def _count_free_instructor_room_slots(
        self,
        instructors: List[dict],
        rooms: List[dict],
        slots: List[str],
        demand: dict,
    ) -> int:
        if not instructors or not rooms:
            return 0

        count = 0
        for day in self.days:
            for slot in slots:
                free_instructors = sum(
                    1
                    for instructor in instructors
                    if self._can_use_instructor(instructor, day, slot, demand)
                )
                if not free_instructors:
                    continue

                free_rooms = sum(
                    1
                    for room in rooms
                    if self._can_use_room(room, day, slot)
                )
                count += min(free_instructors, free_rooms)

        return count

    def _is_instructor_available(self, instructor: dict, day: str, slot: str) -> bool:
        availabilities = instructor.get("availabilities", [])

        if not availabilities:
            return True

        slot_bounds = self._slot_bounds(slot)
        if not slot_bounds:
            return False

        slot_start, slot_end = slot_bounds

        for availability in availabilities:
            if str(availability.get("dayOfWeek")) != day:
                continue

            if availability.get("isAvailable") is False:
                continue

            start = self._norm_hhmm(availability.get("startTime"))
            end = self._norm_hhmm(availability.get("endTime"))

            if self._slot_within_range(slot, start, end):
                return True

        return False

    def _place_session(
        self,
        group_id: str,
        session: dict,
        reserve_resources: bool = True,
    ) -> None:
        self.group_schedules[group_id].append(session)

        if not reserve_resources:
            return

        if session.get("instructorId") is not None:
            self.instructor_schedules[session["instructorId"]].append(session)

        day = session["dayOfWeek"]
        slot = session["timeSlot"]

        self.group_busy.add((group_id, day, slot))

        if session.get("sectionId"):
            self.section_busy.add((session["sectionId"], day, slot))

        for cohort_id in self._cohort_ids_for_session(session):
            self.cohort_busy.add((cohort_id, day, slot))

        if session.get("instructorId") is not None and not session.get("isRecordedOnline"):
            self.instructor_busy.add((session["instructorId"], day, slot))

        if session["roomId"] is not None:
            self.room_schedules[session["roomId"]].append(session)
            self.room_busy.add((session["roomId"], day, slot))

    def _state_checkpoint(self) -> dict:
        return {
            "group_schedules": {
                key: list(value)
                for key, value in self.group_schedules.items()
            },
            "instructor_schedules": {
                key: list(value)
                for key, value in self.instructor_schedules.items()
            },
            "room_schedules": {
                key: list(value)
                for key, value in self.room_schedules.items()
            },
            "group_busy": set(self.group_busy),
            "cohort_busy": set(self.cohort_busy),
            "section_busy": set(self.section_busy),
            "instructor_busy": set(self.instructor_busy),
            "room_busy": set(self.room_busy),
            "session_counter": self.session_counter,
        }

    def _restore_state(self, checkpoint: dict) -> None:
        self.group_schedules = defaultdict(list, checkpoint["group_schedules"])
        self.instructor_schedules = defaultdict(list, checkpoint["instructor_schedules"])
        self.room_schedules = defaultdict(list, checkpoint["room_schedules"])
        self.group_busy = set(checkpoint["group_busy"])
        self.cohort_busy = set(checkpoint["cohort_busy"])
        self.section_busy = set(checkpoint["section_busy"])
        self.instructor_busy = set(checkpoint["instructor_busy"])
        self.room_busy = set(checkpoint["room_busy"])
        self.session_counter = checkpoint["session_counter"]

    def _create_scheduled_session(
        self,
        demand: dict,
        instructor: Optional[dict],
        room: Optional[dict],
        day: str,
        slot: str,
    ) -> dict:
        self.session_counter += 1

        is_recorded_online = (
            demand.get("isOnline") is True
            and demand["courseCode"] in self.online_recorded_courses
        )

        return {
            "sessionId": f"SESSION_{self.session_counter:06d}",
            "sessionType": demand["sessionType"],
            "courseCode": demand["courseCode"],
            "courseName": demand["courseName"],
            "groupId": demand["groupId"],
            "sectionId": demand.get("sectionId"),
            "instructorId": instructor["instructorId"] if instructor else None,
            "instructorName": instructor.get("name") if instructor else None,
            "roomId": room["roomId"] if room else None,
            "roomNumber": room.get("roomNumber") if room else None,
            "roomType": room.get("roomType") if room else None,
            "roomCapacity": self._safe_int(room.get("capacity"), 0) if room else 0,
            "dayOfWeek": day,
            "timeSlot": slot,
            "studentCount": demand["studentCount"],
            "isOnline": demand.get("isOnline", False),
            "isRecordedOnline": is_recorded_online,
        }

    def validate_no_conflicts(self) -> List[str]:
        conflicts = []

        seen_group_sessions = defaultdict(list)
        seen_cohorts = defaultdict(list)
        seen_sections = defaultdict(list)
        seen_instructors = defaultdict(list)
        seen_rooms = defaultdict(list)

        for sessions in self.group_schedules.values():
            for session in sessions:
                day = session["dayOfWeek"]
                slot = session["timeSlot"]
                day_slot = (day, slot)

                group_key = session["groupId"]
                section_id = session.get("sectionId")
                instructor_id = session.get("instructorId")
                instructor_key = instructor_id

                for existing in seen_group_sessions[group_key]:
                    if (
                        existing.get("dayOfWeek") == day
                        and self._slots_overlap(existing.get("timeSlot"), slot)
                        and not self._sessions_can_overlap(existing, session)
                        and self._same_group_sessions_conflict(existing, session)
                    ):
                        conflicts.append(f"Group conflict: {(group_key, *day_slot)}")
                        break
                seen_group_sessions[group_key].append(session)

                if not session.get("isRecordedOnline"):
                    for cohort_id in self._cohort_ids_for_session(session):
                        for existing in seen_cohorts[cohort_id]:
                            if (
                                existing.get("dayOfWeek") == day
                                and self._slots_overlap(existing.get("timeSlot"), slot)
                                and not self._sessions_can_overlap(existing, session)
                            ):
                                conflicts.append(f"Cohort conflict: {(cohort_id, *day_slot)}")
                                break
                        seen_cohorts[cohort_id].append(session)

                if section_id:
                    for existing in seen_sections[section_id]:
                        if existing.get("dayOfWeek") == day and self._slots_overlap(existing.get("timeSlot"), slot):
                            conflicts.append(f"Section conflict: {(section_id, *day_slot)}")
                            break
                    seen_sections[section_id].append(session)

                if instructor_id is not None and not session.get("isRecordedOnline"):
                    for existing in seen_instructors[instructor_key]:
                        if existing.get("dayOfWeek") == day and self._slots_overlap(existing.get("timeSlot"), slot):
                            conflicts.append(f"Instructor conflict: {(instructor_key, *day_slot)}")
                            break
                    seen_instructors[instructor_key].append(session)

                if session["roomId"] is not None:
                    room_key = session["roomId"]

                    for existing in seen_rooms[room_key]:
                        if existing.get("dayOfWeek") == day and self._slots_overlap(existing.get("timeSlot"), slot):
                            conflicts.append(f"Room conflict: {(room_key, *day_slot)}")
                            break
                    seen_rooms[room_key].append(session)

        return conflicts

    def validate_academic_constraints(self) -> List[str]:
        issues = []

        for group_id, sessions in self.group_schedules.items():
            for session in sessions:
                code = session["courseCode"]
                course = self.courses.get(code, {})
                is_online = self._is_online_course(course)

                if session["sessionType"] == "LECTURE" and not is_online:
                    if session.get("roomType") != "GENERAL":
                        issues.append(
                            f"Offline lecture not in GENERAL room: {code} group={group_id}"
                        )

                if session["sessionType"] == "SECTION":
                    if is_online and not session.get("isProject"):
                        issues.append(
                            f"Online course has a section: {code} group={group_id}"
                        )

                if is_online:
                    if session["roomId"] is not None:
                        issues.append(
                            f"Online course assigned a room: {code} group={group_id}"
                        )

                    if (
                        session["timeSlot"] not in self.online_slots
                        and not self._slot_within_any_range(session["timeSlot"], self.online_slots)
                    ):
                        issues.append(
                            f"Online course not in online slot: {code} group={group_id}"
                        )

        return issues

    def _build_group_schedules_output(self) -> List[dict]:
        result = []
        for group_id in sorted(self.group_details, key=self._group_sort_key):
            details = {
                key: value
                for key, value in self.group_details[group_id].items()
                if key != "cohortIds"
            }
            sessions = self._sort_sessions(self.group_schedules.get(group_id, []))
            section_ids = list(details.get("sectionIds") or [])
            lectures = [
                session
                for session in sessions
                if not session.get("sectionId")
            ]
            sections = [
                {
                    "sectionGroupId": section_id,
                    "sectionLetter": section_id.replace(group_id, "", 1),
                    "sessions": [
                        session
                        for session in sessions
                        if session.get("sectionId") == section_id
                    ],
                }
                for section_id in section_ids
            ]
            result.append({
                **details,
                "lectureGroupId": group_id,
                "lectures": lectures,
                "sections": sections,
                "sessions": sessions,
                "totalSessions": len(sessions),
            })

        return sorted(result, key=self._course_output_sort_key)

    def _build_student_group_schedules_output(self) -> List[dict]:
        result = []

        for lecture_group_id in sorted(self.group_details, key=self._group_sort_key):
            details = self.group_details[lecture_group_id]
            sessions = self._sort_sessions(self.group_schedules.get(lecture_group_id, []))
            section_ids = list(details.get("sectionIds") or [])
            lectures = [
                session
                for session in sessions
                if not session.get("sectionId")
            ]

            if not section_ids:
                result.append({
                    "groupId": lecture_group_id,
                    "lectureGroupId": lecture_group_id,
                    "level": details.get("level"),
                    "studentCount": details.get("studentCount", 0),
                    "courseCodes": details.get("courseCodes", []),
                    "lectures": lectures,
                    "sections": [
                        session
                        for session in sessions
                        if session.get("sectionId")
                    ],
                    "sessions": sessions,
                    "totalSessions": len(sessions),
                })
                continue

            for section_id in section_ids:
                section_sessions = [
                    session
                    for session in sessions
                    if session.get("sectionId") == section_id
                ]
                student_count = max(
                    [self._safe_int(session.get("studentCount"), 0) for session in section_sessions]
                    or [0]
                )
                combined_sessions = self._sort_sessions(lectures + section_sessions)

                result.append({
                    "groupId": section_id,
                    "sectionGroupId": section_id,
                    "lectureGroupId": lecture_group_id,
                    "sectionLetter": section_id.replace(lecture_group_id, "", 1),
                    "level": details.get("level"),
                    "studentCount": student_count,
                    "courseCodes": details.get("courseCodes", []),
                    "lectures": lectures,
                    "sections": section_sessions,
                    "sessions": combined_sessions,
                    "totalSessions": len(combined_sessions),
                })

        return result

    def _build_course_table_output(self) -> dict:
        levels = []

        groups_by_level = defaultdict(list)
        for group_id, details in self.group_details.items():
            groups_by_level[details.get("level")].append(group_id)

        for level in sorted(groups_by_level):
            groups = []
            for group_id in sorted(groups_by_level[level], key=self._group_sort_key):
                details = dict(self.group_details[group_id])
                group = {
                    "groupId": group_id,
                    "studentCount": details.get("studentCount", 0),
                    "departments": details.get("departments", []),
                    "displayOnlyCourses": self._display_only_courses_for_group(group_id),
                    "sessions": self._sort_sessions(self.group_schedules.get(group_id, [])),
                }

                if "courseCodes" in details:
                    group["courseCodes"] = details["courseCodes"]

                groups.append(group)

            levels.append({
                "level": level,
                "groups": groups,
            })

        return {"levels": levels}

    def _build_course_sessions_output(self, category: str) -> List[dict]:
        result = []

        for code, course in sorted(
            self.courses.items(),
            key=lambda item: self._course_output_sort_key(item[1]),
        ):
            is_arabic = course.get("isArabicOnline") is True
            if category == "arabic" and not is_arabic:
                continue
            if category == "college" and is_arabic:
                continue

            sessions = [
                session
                for group_sessions in self.group_schedules.values()
                for session in group_sessions
                if session.get("courseCode") == code
            ]
            session_student_count = max(
                [self._safe_int(session.get("studentCount"), 0) for session in sessions]
                or [0]
            )
            total_student_count = self._safe_int(course.get("totalStudentCount"), 0)
            primary_student_count = sum(self._course_level_student_counts(course).values())
            if self._is_project_course(course):
                total_student_count = total_student_count or session_student_count
                primary_student_count = primary_student_count or session_student_count

            result.append({
                "courseCode": code,
                "courseName": course.get("courseName", code),
                "courseNameAr": course.get("courseNameAr"),
                "levels": self._normalize_levels(course),
                "departments": self._normalize_departments(course.get("departments")),
                "totalStudentCount": total_student_count,
                "primaryStudentCount": primary_student_count,
                "lectureDurationMinutes": self._course_lecture_duration(course),
                "sectionDurationMinutes": (
                    self._course_section_duration(course)
                    if course.get("labType") is not None
                    else None
                ),
                "sessions": self._sort_sessions(sessions),
                "totalSessions": len(sessions),
                "status": "SCHEDULED" if sessions else "UNSCHEDULED",
            })

        return sorted(result, key=self._course_output_sort_key)

    def _simplify_courses_output(self, courses: List[dict]) -> List[dict]:
        return [
            {
                "courseCode": course.get("courseCode"),
                "courseName": course.get("courseName"),
                "courseNameAr": course.get("courseNameAr"),
                "level": min(
                    [self._safe_int(level, 999) for level in course.get("levels") or []]
                    or [999]
                ),
                "levels": course.get("levels") or [],
                "departments": course.get("departments") or [],
                "totalStudentCount": self._safe_int(course.get("totalStudentCount"), 0),
                "sessions": [
                    self._simplify_session_output(session)
                    for session in course.get("sessions") or []
                ],
                "totalSessions": self._safe_int(course.get("totalSessions"), 0),
                "status": course.get("status"),
            }
            for course in sorted(courses, key=self._course_output_sort_key)
        ]

    def _simplify_session_output(self, session: dict) -> dict:
        simple = {
            "sessionId": session.get("sessionId"),
            "sessionType": session.get("sessionType"),
            "courseCode": session.get("courseCode"),
            "groupId": session.get("groupId"),
            "sectionId": session.get("sectionId"),
            "instructorId": session.get("instructorId"),
            "instructorName": session.get("instructorName"),
            "roomId": session.get("roomId"),
            "roomNumber": session.get("roomNumber"),
            "roomType": session.get("roomType"),
            "roomCapacity": self._session_room_capacity(session),
            "dayOfWeek": session.get("dayOfWeek"),
            "timeSlot": session.get("timeSlot"),
            "studentCount": self._safe_int(session.get("studentCount"), 0),
            "isOnline": session.get("isOnline", False),
        }

        for key in ("projectComponent", "isProject", "isArabicOnline", "level"):
            if key in session:
                simple[key] = session.get(key)

        return simple

    def _simplify_instructor_schedules_output(self, instructors: List[dict]) -> List[dict]:
        return [
            {
                "instructorId": instructor.get("instructorId"),
                "instructorName": instructor.get("instructorName"),
                "instructorType": instructor.get("instructorType"),
                "sessions": [
                    self._simplify_session_output(session)
                    for session in instructor.get("sessions") or []
                ],
                "totalSessions": self._safe_int(instructor.get("totalSessions"), 0),
            }
            for instructor in instructors
            if instructor.get("sessions")
        ]

    def _simplify_room_schedules_output(self, rooms: List[dict]) -> List[dict]:
        return [
            {
                "roomId": room.get("roomId"),
                "roomNumber": room.get("roomNumber"),
                "roomType": room.get("roomType"),
                "capacity": self._safe_int(room.get("capacity"), 0),
                "sessions": [
                    self._simplify_session_output(session)
                    for session in room.get("sessions") or []
                ],
                "totalSessions": self._safe_int(room.get("totalSessions"), 0),
            }
            for room in rooms
            if room.get("sessions")
        ]

    def _build_capacity_issues_output(self) -> List[dict]:
        issues_by_session = {}

        for sessions in self.group_schedules.values():
            for session in sessions:
                if session.get("isOnline"):
                    continue

                student_count = self._safe_int(session.get("studentCount"), 0)
                room_capacity = self._session_room_capacity(session)
                if room_capacity <= 0 or student_count <= room_capacity:
                    continue

                session_id = session.get("sessionId")
                issues_by_session[session_id] = {
                    "sessionId": session_id,
                    "courseCode": session.get("courseCode"),
                    "courseName": session.get("courseName"),
                    "sessionType": session.get("sessionType"),
                    "groupId": session.get("groupId"),
                    "sectionId": session.get("sectionId"),
                    "instructorId": session.get("instructorId"),
                    "instructorName": session.get("instructorName"),
                    "roomId": session.get("roomId"),
                    "roomNumber": session.get("roomNumber"),
                    "roomType": session.get("roomType"),
                    "dayOfWeek": session.get("dayOfWeek"),
                    "timeSlot": session.get("timeSlot"),
                    "studentCount": student_count,
                    "roomCapacity": room_capacity,
                    "overflowBy": student_count - room_capacity,
                }

        return sorted(
            issues_by_session.values(),
            key=lambda item: (
                self._safe_int(item.get("roomId"), 999999),
                str(item.get("dayOfWeek") or ""),
                str(item.get("timeSlot") or ""),
                str(item.get("courseCode") or ""),
                str(item.get("groupId") or ""),
                str(item.get("sectionId") or ""),
            ),
        )

    def _session_room_capacity(self, session: dict) -> int:
        capacity = self._safe_int(session.get("roomCapacity"), 0)
        if capacity > 0:
            return capacity

        room_id = session.get("roomId")
        room = self.rooms.get(room_id) if room_id is not None else None
        if room:
            return self._safe_int(room.get("capacity"), 0)

        return 0

    def _display_only_courses_for_group(self, group_id: str) -> List[dict]:
        details = self.group_details.get(group_id, {})
        level = details.get("level")
        group_departments = set(self._normalize_departments(details.get("departments")))
        result = []

        for course in self.courses.values():
            if not self._is_display_only_course(course):
                continue

            if level not in set(self._normalize_levels(course)):
                continue

            course_departments = set(self._normalize_departments(course.get("departments")))
            if course_departments and group_departments and not course_departments.intersection(group_departments):
                continue

            result.append({
                "courseCode": course.get("courseCode"),
                "courseName": course.get("courseName"),
                "courseNameAr": course.get("courseNameAr"),
                "levels": self._normalize_levels(course),
                "departments": self._normalize_departments(course.get("departments")),
                "scheduleMode": course.get("scheduleMode") or "DISPLAY_ONLY",
                **self.project_display_details.get(course.get("courseCode"), {}),
            })

        return sorted(result, key=lambda item: item["courseCode"])

    def _build_aptech_courses_output(self) -> List[dict]:
        result = []
        busy = set()

        for course in sorted(self.aptech_courses, key=self._course_output_sort_key):
            code = course["courseCode"]
            course_instructor_ids = set(course.get("instructorIds") or [])
            course_instructor_names = {
                self._normalized_person_name(course.get("instructorName")),
                self._normalized_person_name(course.get("instructorNameAr")),
            }
            course_instructor_names.discard("")
            is_aptech_computer = self._is_aptech_computer_course(course)
            matching = []
            seen_instructor_ids = set()
            instructor_pool = list(self.aptech_instructors.values()) + list(self.instructors.values())

            for instructor in instructor_pool:
                instructor_id = instructor.get("instructorId")
                if instructor_id in seen_instructor_ids:
                    continue

                if (
                    code in self._assigned_course_codes(instructor)
                    or instructor_id in course_instructor_ids
                ):
                    matching.append(instructor)
                    seen_instructor_ids.add(instructor_id)

            if course_instructor_names:
                for instructor in instructor_pool:
                    instructor_id = instructor.get("instructorId")
                    if instructor_id in seen_instructor_ids:
                        continue

                    instructor_names = {
                        self._normalized_person_name(instructor.get("name")),
                        self._normalized_person_name(instructor.get("nameAr")),
                    }

                    if course_instructor_names.intersection(instructor_names):
                        matching.append(instructor)
                        seen_instructor_ids.add(instructor_id)

            if is_aptech_computer:
                assistant_matches = [
                    instructor
                    for instructor in matching
                    if instructor.get("instructorType") == "TA"
                ]
                if assistant_matches:
                    matching = assistant_matches

            matching.sort(
                key=lambda instructor: (
                    0 if instructor.get("instructorType") == "TA" else 1,
                    len(self.instructor_schedules.get(instructor.get("instructorId"), [])),
                    instructor.get("instructorId") or 0,
                )
            )

            assigned = matching[0] if matching else None
            instructor_id = (
                assigned.get("instructorId")
                if assigned
                else (next(iter(course_instructor_ids), None) or course.get("instructorId"))
            )
            instructor_name = assigned.get("name") if assigned else course.get("instructorName")
            instructor_type = assigned.get("instructorType") if assigned else None
            availabilities = []

            if isinstance(course.get("availabilities"), list) and course["availabilities"]:
                availabilities = course["availabilities"]
            elif assigned and assigned.get("availabilities"):
                availabilities = assigned["availabilities"]

            identity_key = self._aptech_course_identity_key(course, instructor_id, instructor_name)
            share_count = self._aptech_identity_course_count(identity_key)
            possible_count = self._aptech_possible_assignment_count(instructor_id, availabilities)
            max_sessions = (
                math.ceil(possible_count / share_count)
                if share_count > 1 and possible_count > 0
                else None
            )
            assignments = self._choose_aptech_assignments(
                instructor_id,
                instructor_name,
                instructor_type,
                course,
                availabilities,
                busy,
                max_sessions=max_sessions,
            )
            primary_assignment = assignments[0] if assignments else {}

            result.append({
                "courseCode": code,
                "courseName": course.get("courseName", code),
                "courseNameAr": course.get("courseNameAr"),
                "assignedInstructorId": instructor_id,
                "assignedInstructorName": instructor_name,
                "assignedInstructorType": instructor_type,
                "levels": self._normalize_levels(course),
                "departments": self._normalize_departments(course.get("departments")),
                "totalStudentCount": self._safe_int(course.get("totalStudentCount"), 0),
                "dayOfWeek": primary_assignment.get("dayOfWeek"),
                "timeSlot": primary_assignment.get("timeSlot"),
                "sessions": assignments,
                "totalSessions": len(assignments),
                "status": "SCHEDULED" if assignments else "UNSCHEDULED",
            })

        return sorted(result, key=self._course_output_sort_key)

    def _aptech_course_identity_key(self, course: dict, instructor_id=None, instructor_name=None):
        if instructor_id is not None:
            return ("id", instructor_id)

        name = (
            instructor_name
            or course.get("instructorName")
            or course.get("name")
            or course.get("instructorNameAr")
        )
        normalized_name = self._normalized_person_name(name)
        if normalized_name:
            return ("name", normalized_name)

        return ("course", course.get("courseCode"))

    def _aptech_identity_course_count(self, identity_key) -> int:
        count = 0
        for course in self.aptech_courses:
            if self._aptech_course_identity_key(course) == identity_key:
                count += 1

        return max(1, count)

    def _aptech_possible_assignment_count(
        self,
        instructor_id,
        availabilities: List[dict],
    ) -> int:
        count = 0
        for availability in self._aptech_search_availabilities(availabilities):
            day = availability.get("dayOfWeek")
            if not day:
                continue

            for slot in self._aptech_slots_for_availability(availability):
                if (
                    instructor_id is not None
                    and self._has_instructor_time_conflict(instructor_id, day, slot)
                ):
                    continue
                count += 1

        return count

    def _aptech_search_availabilities(self, availabilities: List[dict]) -> List[dict]:
        search_availabilities = list(availabilities or [])
        if search_availabilities:
            return search_availabilities

        slots = self.input_data.get("aptechTimeSlots") or self.regular_slots
        return [
            {
                "dayOfWeek": day,
                "startTime": slot.split("-", 1)[0],
                "endTime": slot.split("-", 1)[1],
            }
            for day in self.days
            for slot in slots
            if "-" in slot
        ]

    def _is_aptech_computer_course(self, course: dict) -> bool:
        code = str(course.get("courseCode") or "").strip().upper()
        name = str(course.get("courseName") or "").strip().upper()
        name_ar = str(course.get("courseNameAr") or "").strip().upper()

        return (
            code.endswith("-P2")
            or "APTECH COMPUTER" in name
            or "COMPUTER" in name and "APTECH" in name
            or "Ø§Ø¨ØªÙƒ" in name_ar
            or "Ø§Ø¨ØªÙŠÙƒ" in name_ar
        )

    def _choose_aptech_assignment(
        self,
        instructor_id,
        instructor_name,
        availabilities: List[dict],
        busy: set,
    ) -> dict:
        identity = instructor_id if instructor_id is not None else instructor_name
        search_availabilities = list(availabilities or [])

        if not search_availabilities:
            slots = self.input_data.get("aptechTimeSlots") or self.regular_slots
            search_availabilities = [
                {
                    "dayOfWeek": day,
                    "startTime": slot.split("-", 1)[0],
                    "endTime": slot.split("-", 1)[1],
                }
                for day in self.days
                for slot in slots
                if "-" in slot
            ]

        for availability in search_availabilities:
            day = availability.get("dayOfWeek")
            if not day:
                continue

            for slot in self._aptech_slots_for_availability(availability):
                key = (identity, day, slot)
                if key in busy:
                    continue
                if (
                    instructor_id is not None
                    and self._has_instructor_time_conflict(instructor_id, day, slot)
                ):
                    continue

                busy.add(key)
                return {"dayOfWeek": day, "timeSlot": slot}

        return {"dayOfWeek": None, "timeSlot": None}

    def _choose_aptech_assignments(
        self,
        instructor_id,
        instructor_name,
        instructor_type,
        course: dict,
        availabilities: List[dict],
        busy: set,
        max_sessions: Optional[int] = None,
    ) -> List[dict]:
        identity = instructor_id if instructor_id is not None else instructor_name
        search_availabilities = self._aptech_search_availabilities(availabilities)
        assignments = []
        code = course.get("courseCode")
        course_name = course.get("courseName", code)
        course_name_ar = course.get("courseNameAr")
        levels = self._normalize_levels(course)
        primary_level = levels[0] if levels else None
        seen_slots = set()

        for availability in search_availabilities:
            day = availability.get("dayOfWeek")
            if not day:
                continue

            for slot in self._aptech_slots_for_availability(availability):
                key = (identity, day, slot)
                if key in busy or key in seen_slots:
                    continue
                if (
                    instructor_id is not None
                    and self._has_instructor_time_conflict(instructor_id, day, slot)
                ):
                    continue

                busy.add(key)
                seen_slots.add(key)
                start, end = slot.split("-", 1)
                self.session_counter += 1
                assignments.append({
                    "sessionId": f"SESSION_{self.session_counter:06d}",
                    "sessionType": "APTECH",
                    "courseCode": code,
                    "courseName": course_name,
                    "courseNameAr": course_name_ar,
                    "groupId": f"APTECH-{code}-G1",
                    "sectionId": None,
                    "level": primary_level,
                    "levels": levels,
                    "dayOfWeek": day,
                    "startTime": start,
                    "endTime": end,
                    "timeSlot": slot,
                    "instructorId": instructor_id,
                    "instructorName": instructor_name,
                    "instructorType": instructor_type,
                    "roomId": None,
                    "roomNumber": "ONLINE",
                    "roomType": "ONLINE",
                    "roomCapacity": 0,
                    "studentCount": self._safe_int(course.get("totalStudentCount"), 0),
                    "isAptech": True,
                    "isOnline": True,
                })
                if max_sessions is not None and len(assignments) >= max_sessions:
                    return self._sort_aptech_sessions(assignments)

        return self._sort_aptech_sessions(assignments)

    def _aptech_slots_for_availability(self, availability: dict) -> List[str]:
        allowed_slots = self.input_data.get("aptechTimeSlots") or []
        start = self._norm_hhmm(availability.get("startTime"))
        end = self._norm_hhmm(availability.get("endTime"))

        if allowed_slots:
            matching = [
                slot
                for slot in allowed_slots
                if self._slot_within_range(slot, start, end)
            ]

            return matching

        if start and end:
            return [f"{start}-{end}"]

        return []

    def _slot_within_range(self, slot: str, start: str, end: str) -> bool:
        slot_bounds = self._slot_bounds(slot)
        range_start = self._time_to_minutes(start)
        range_end = self._time_to_minutes(end)

        if not slot_bounds or range_start is None or range_end is None:
            return False

        slot_start, slot_end = slot_bounds
        return range_start <= slot_start and slot_end <= range_end

    def _slot_within_any_range(self, slot: str, ranges: List[str]) -> bool:
        return any(
            self._slot_within_range(slot, *candidate.split("-", 1))
            for candidate in ranges or []
            if isinstance(candidate, str) and "-" in candidate
        )

    def _build_instructor_schedules_output(self) -> List[dict]:
        result = []

        for instructor_id in sorted(self.instructor_schedules):
            instructor = self.instructors.get(instructor_id, {})
            sessions = self._sort_sessions(self.instructor_schedules[instructor_id])

            result.append({
                "instructorId": instructor_id,
                "instructorName": instructor.get("name", f"Instructor {instructor_id}"),
                "instructorType": instructor.get("instructorType"),
                "sessions": sessions,
                "totalSessions": len(sessions),
            })

        return result

    def _build_room_schedules_output(self) -> List[dict]:
        total_slots = max(1, len(self.days) * len(self.regular_slots))
        result = []

        for room_id in sorted(self.rooms):
            room = self.rooms[room_id]
            sessions = self._sort_sessions(self.room_schedules.get(room_id, []))

            result.append({
                "roomId": room_id,
                "roomNumber": room.get("roomNumber"),
                "roomType": room.get("roomType"),
                "capacity": room.get("capacity"),
                "sessions": sessions,
                "totalSessions": len(sessions),
                "utilizationRate": round(len(sessions) / total_slots, 4),
            })

        return result

    def _build_optimization_summary(self) -> dict:
        groups = []
        total_campus_days = 0
        total_gaps = 0
        total_single_session_days = 0

        for group_id in sorted(self.group_details, key=self._group_sort_key):
            sessions = self._sort_sessions(self.group_schedules.get(group_id, []))
            summary = self._summarize_group_quality(group_id, sessions)
            groups.append(summary)
            total_campus_days += summary["campusDays"]
            total_gaps += summary["gaps"]
            total_single_session_days += summary["singleSessionDays"]

        group_count = max(1, len(groups))

        return {
            "averageCampusDaysPerGroup": round(total_campus_days / group_count, 2),
            "totalGaps": total_gaps,
            "totalSingleSessionDays": total_single_session_days,
            "groups": groups,
        }

    def _summarize_group_quality(self, group_id: str, sessions: List[dict]) -> dict:
        slots = list(dict.fromkeys(self.regular_slots + self.online_slots))
        slot_order = {slot: index for index, slot in enumerate(slots)}
        by_day = defaultdict(list)

        for session in sessions:
            if session.get("isOnline"):
                continue

            by_day[session["dayOfWeek"]].append(session)

        gaps = 0
        single_session_days = 0

        for day_sessions in by_day.values():
            indexes = sorted(
                slot_order[session["timeSlot"]]
                for session in day_sessions
                if session["timeSlot"] in slot_order
            )

            if len(indexes) == 1:
                single_session_days += 1

            if len(indexes) > 1:
                gaps += (indexes[-1] - indexes[0] + 1) - len(set(indexes))

        return {
            "groupId": group_id,
            "campusDays": len(by_day),
            "gaps": gaps,
            "singleSessionDays": single_session_days,
            "totalSessions": len(sessions),
        }

    def _normalize_courses(self) -> Dict[str, dict]:
        raw_courses = []

        for item in self.input_data.get("courses") or []:
            if isinstance(item, dict):
                raw_courses.append({**item, "_courseCategory": "college"})

        for item in self.input_data.get("regularCourses") or []:
            if isinstance(item, dict):
                raw_courses.append({**item, "_courseCategory": "college"})

        for item in self.input_data.get("projectCourses") or []:
            if isinstance(item, dict):
                raw_courses.append({
                    **item,
                    "labType": item.get("labType") or "PROJECT",
                    "scheduleMode": item.get("scheduleMode") or "PROJECT",
                    "_courseCategory": "college",
                })
            elif item:
                raw_courses.append({
                    "courseCode": item,
                    "labType": "PROJECT",
                    "scheduleMode": "PROJECT",
                    "_courseCategory": "college",
                })

        for item in self.input_data.get("onlineCourses") or []:
            if isinstance(item, dict):
                code = self._course_code(item)
                if code in self.arabic_online_courses or item.get("isArabicOnline") is True:
                    raw_courses.append({
                        **item,
                        "labType": None,
                        "isArabicOnline": True,
                        "_courseCategory": "arabic",
                    })

        for item in self.input_data.get("arabicCourses") or []:
            if isinstance(item, dict):
                raw_courses.append({
                    **item,
                    "labType": None,
                    "isArabicOnline": True,
                    "_courseCategory": "arabic",
                })

        courses = {}

        for item in raw_courses:
            if not isinstance(item, dict):
                continue

            code = self._course_code(item)

            if code == "STRING":
                continue

            if not code or code in self.ignored_online_courses:
                if code:
                    self.skipped_courses[code] = "Course is configured as ignored online course."
                continue

            normalized = dict(item)
            normalized["courseCode"] = code
            normalized["courseName"] = item.get("courseName") or code
            if code in self.arabic_online_courses:
                normalized["isArabicOnline"] = True
            normalized["courseCategory"] = (
                "arabic"
                if normalized.get("isArabicOnline") is True
                else str(item.get("courseCategory") or item.get("_courseCategory") or "college")
                .strip()
                .lower()
            )
            normalized["levels"] = self._normalize_levels(item)
            normalized["level"] = normalized["levels"][0]
            normalized["academicLevel"] = normalized["levels"][0]
            normalized["departments"] = self._normalize_departments(item.get("departments"))
            if all(level <= 2 for level in normalized["levels"]):
                normalized["departments"] = []
            normalized["enrollmentCount"] = self._course_student_count(item)
            normalized["totalStudentCount"] = self._course_student_count(item)
            normalized["studentBreakdown"] = self._normalize_student_breakdown(
                item.get("studentBreakdown")
            )
            normalized["labType"] = (
                None
                if normalized.get("isArabicOnline") is True
                else self._normalized_lab_type(item.get("labType"))
            )
            if (
                normalized["labType"] == "LAB_ONLY"
                and self._course_allows_general_section_rooms(item)
            ):
                normalized["labType"] = "GENERAL_LAB"
            normalized["instructorIds"] = self._extract_course_instructor_ids(item)
            normalized["lectureDurationMinutes"] = self._course_lecture_duration(normalized)
            normalized["sectionDurationMinutes"] = self._course_section_duration(normalized)

            if code in courses:
                courses[code] = self._merge_course_records(courses[code], normalized)
            else:
                courses[code] = normalized

        return courses

    def _normalize_aptech_courses(self) -> List[dict]:
        courses = []

        for item in self.input_data.get("aptechCourses") or []:
            if not isinstance(item, dict):
                continue

            code = self._course_code(item)
            if not code:
                continue

            courses.append({
                **item,
                "courseCode": code,
                "courseName": item.get("courseName") or code,
                "totalStudentCount": self._safe_int(
                    item.get("totalStudentCount", item.get("enrollmentCount")),
                    0,
                ),
                "instructorIds": self._extract_course_instructor_ids(item),
            })

        return courses

    def _instructors_with_source(self, raw_instructors, source: str) -> List[dict]:
        result = []

        for item in raw_instructors or []:
            if not isinstance(item, dict):
                continue

            tagged = dict(item)
            sources = set(self._normalize_instructor_sources(tagged.get("sourceCategories")))
            sources.update(self._normalize_instructor_sources(source))
            tagged["sourceCategories"] = sorted(sources)
            result.append(tagged)

        return result

    def _normalize_instructor_sources(self, sources) -> List[str]:
        if sources is None:
            return []

        if isinstance(sources, str):
            sources = [sources]

        result = []
        for source in sources or []:
            value = str(source).strip().lower()
            if value in {"regular", "college", "faculty"}:
                value = "college"
            elif value in {"arabic", "online", "university"}:
                value = "arabic"
            elif value in {"all", "generic", "any"}:
                value = "all"
            else:
                continue

            if value not in result:
                result.append(value)

        return result

    def _normalize_instructors(self, raw_instructors: Iterable[dict]) -> Dict[int, dict]:
        instructors = {}

        for item in raw_instructors or []:
            if not isinstance(item, dict):
                continue

            instructor_id = self._safe_int(item.get("instructorId"), None)

            if instructor_id is None:
                continue

            instructor_type = str(item.get("instructorType") or "DOCTOR").strip().upper()

            if instructor_type in {"TECHNICAL ASSISTANT", "TECHNICAL_ASSISTANT", "ASSISTANT"}:
                instructor_type = "TA"

            if instructor_type not in {"DOCTOR", "TA", "APTECH"}:
                instructor_type = "DOCTOR"

            normalized = {
                **item,
                "instructorId": instructor_id,
                "name": item.get("name") or f"Instructor {instructor_id}",
                "instructorType": instructor_type,
                "assignedCourses": self._normalize_assigned_courses(
                    item.get("assignedCourses", [])
                ),
                "availabilities": self._normalize_availabilities(item.get("availabilities")),
                "sourceCategories": self._normalize_instructor_sources(
                    item.get("sourceCategories")
                ),
            }

            if instructor_id in instructors:
                existing = instructors[instructor_id]
                existing_codes = {
                    self._course_code(course)
                    for course in existing.get("assignedCourses", [])
                    if self._course_code(course)
                }
                merged_courses = list(existing.get("assignedCourses", []))

                for course in normalized.get("assignedCourses", []):
                    code = self._course_code(course)
                    if code and code not in existing_codes:
                        merged_courses.append(course)
                        existing_codes.add(code)

                existing["assignedCourses"] = merged_courses
                existing["availabilities"] = (
                    existing.get("availabilities", [])
                    or normalized.get("availabilities", [])
                )
                existing["instructorType"] = (
                    "DOCTOR"
                    if "DOCTOR" in {existing.get("instructorType"), normalized.get("instructorType")}
                    else existing.get("instructorType") or normalized.get("instructorType")
                )
                existing["sourceCategories"] = sorted(
                    set(existing.get("sourceCategories") or [])
                    | set(normalized.get("sourceCategories") or [])
                )
            else:
                instructors[instructor_id] = normalized

        return instructors

    def _normalize_availabilities(self, availabilities) -> List[dict]:
        if not isinstance(availabilities, list):
            return []

        result = []
        seen = set()

        for availability in availabilities:
            if not isinstance(availability, dict):
                continue

            day = availability.get("dayOfWeek")
            start = self._norm_hhmm(availability.get("startTime"))
            end = self._norm_hhmm(availability.get("endTime"))

            if not day or not start or not end:
                continue

            key = (str(day), start, end)
            if key in seen:
                continue

            seen.add(key)
            result.append({
                **availability,
                "dayOfWeek": str(day),
                "startTime": start,
                "endTime": end,
            })

        return result

    def _normalize_rooms(self, raw_rooms: Iterable[dict]) -> Dict[int, dict]:
        rooms = {}

        for item in raw_rooms or []:
            if not isinstance(item, dict):
                continue

            room_id = self._safe_int(item.get("roomId"), None)

            if room_id is None:
                continue

            room_number = str(item.get("roomNumber") or room_id)
            room_type = str(item.get("roomType") or "GENERAL").strip().upper()
            room_number_key = room_number.strip().upper()

            if room_id in self.physics_lab_room_ids or room_number in self.physics_lab_room_numbers:
                room_type = "PH101_LA"
            elif room_number_key in self.room_type_overrides:
                room_type = self.room_type_overrides[room_number_key]
            elif room_type in {"LECTURE", "LECTURE_HALL", "GENERAL_LAB"}:
                room_type = "GENERAL"
            elif room_type == "LAB":
                room_type = "LAB_ONLY"
            elif room_type in {"PHYSICS", "PHYSICS_LAB", "PH101_LAB"}:
                room_type = "PH101_LA"
            elif room_type == "ONLINE":
                room_type = "ONLINE"

            capacity = self._safe_int(item.get("capacity"), 0)
            if room_number_key in self.room_capacity_overrides:
                capacity = max(capacity, self.room_capacity_overrides[room_number_key])
            if room_type != "ONLINE":
                capacity = max(capacity, self.min_effective_room_capacity)

            rooms[room_id] = {
                **item,
                "roomId": room_id,
                "roomNumber": room_number,
                "roomType": room_type,
                "capacity": capacity,
            }

        return rooms

    def _filter_courses_without_required_staff(self) -> None:
        for code in list(self.courses):
            if self._is_display_only_course(self.courses[code]) or self._is_project_course(self.courses[code]):
                continue

            if self.courses[code].get("isArabicOnline") is True:
                continue

            instructors = [
                instructor
                for instructor in self.instructors.values()
                if self._instructor_matches_course_category(instructor, self.courses[code])
                and (
                    code in self._assigned_course_codes(instructor)
                    or instructor.get("instructorId") in set(self.courses[code].get("instructorIds") or [])
                )
            ]

            if not instructors:
                self.skipped_courses[code] = "No assigned instructors."
                del self.courses[code]
                continue

            if self._is_online_course(self.courses[code]):
                has_doctor = any(
                    instructor.get("instructorType") == "DOCTOR"
                    for instructor in instructors
                )

                if not has_doctor:
                    self.skipped_courses[code] = "Online course has no doctor."
                    del self.courses[code]

    def _extract_online_course_codes(self, items: Iterable) -> set:
        codes = set()

        for item in items or []:
            if isinstance(item, str):
                code = item.strip().upper()
                if code in self.arabic_online_courses:
                    codes.add(code)

            elif isinstance(item, dict):
                code = self._course_code(item)

                if code in self.arabic_online_courses or item.get("isArabicOnline") is True:
                    codes.add(code)

        return codes

    def _is_online_course(self, course: dict) -> bool:
        return (
            course.get("isArabicOnline") is True
            or self._is_project_course(course)
            or course.get("isOnline") is True
            or self._course_code(course) in self.online_course_codes
        )

    def _is_display_only_course(self, course: dict) -> bool:
        code = self._course_code(course)
        schedule_mode = str(course.get("scheduleMode") or "").strip().upper()

        return (
            code in self.display_only_courses
            or schedule_mode in {"DISPLAY_ONLY", "INFO_ONLY"}
        )

    def _is_project_course(self, course: dict) -> bool:
        code = self._course_code(course)
        lab_type = str(course.get("labType") or "").strip().upper()
        schedule_mode = str(course.get("scheduleMode") or "").strip().upper()

        return code in self.project_courses or lab_type == "PROJECT" or schedule_mode == "PROJECT"

    def _has_instructor_dependent_courses(self) -> bool:
        return any(
            not self._is_project_course(course)
            and course.get("isArabicOnline") is not True
            for course in self.courses.values()
        )

    def _has_offline_courses(self) -> bool:
        return any(
            not self._is_online_course(course)
            for course in self.courses.values()
        )

    def _target_sections_count(self, group_size: int) -> int:
        by_capacity = max(1, math.ceil(group_size / self.max_section_size))
        return max(self.min_sections_per_lecture_group, by_capacity)

    def _course_group_size(self, course_code: str, group_id: str) -> int:
        size = self.course_group_sizes.get(course_code, {}).get(group_id)
        if size:
            return size
        return self.group_sizes.get(group_id, 0)

    def _section_ids_for_group_size(self, group_id: str, group_size: int) -> List[str]:
        return [
            self._section_label(group_id, index)
            for index in range(1, self._target_sections_count(group_size) + 1)
        ]

    def _distribute_group_to_sections(
        self,
        group_size: int,
        section_count: int,
        max_section_size: int,
    ) -> Optional[List[int]]:
        if section_count <= 0:
            return None

        minimum_by_capacity = max(1, math.ceil(group_size / max(1, max_section_size)))
        section_count = max(section_count, minimum_by_capacity)

        return self._split_evenly(group_size, section_count)

    def _split_evenly(self, total: int, parts: int) -> List[int]:
        if parts <= 0:
            return []

        base = total // parts
        remainder = total % parts

        return [
            base + (1 if index < remainder else 0)
            for index in range(parts)
        ]

    def _allocate_counts_across_keys(self, total: int, weights: Dict[str, int]) -> Dict[str, int]:
        keys = [key for key, weight in weights.items() if self._safe_int(weight, 0) > 0]
        if total <= 0 or not keys:
            return {}

        if total <= len(keys):
            ranked = sorted(keys, key=lambda key: (-self._safe_int(weights[key], 0), key))
            return {key: 1 for key in ranked[:total]}

        allocation = {key: 1 for key in keys}
        remaining = total - len(keys)
        weight_total = sum(self._safe_int(weights[key], 0) for key in keys)

        if remaining <= 0 or weight_total <= 0:
            return allocation

        shares = []
        assigned_extra = 0
        for key in keys:
            exact = remaining * self._safe_int(weights[key], 0) / weight_total
            extra = int(math.floor(exact))
            allocation[key] += extra
            assigned_extra += extra
            shares.append((exact - extra, self._safe_int(weights[key], 0), key))

        for _, _, key in sorted(shares, reverse=True)[: remaining - assigned_extra]:
            allocation[key] += 1

        return allocation

    def _preferred_slots_for_course(self, course_code: str, session_type: str = "LECTURE") -> List[str]:
        course = self.courses.get(course_code, {})
        level = self._course_level(course)
        duration = (
            self._course_section_duration(course)
            if session_type == "SECTION"
            else self._course_lecture_duration(course)
        )
        base_slots = list(self.regular_slots)

        if level in {3, 4}:
            preferred = [
                slot
                for slot in base_slots
                if slot == "13:00-15:00"
            ]

            base_slots = preferred + [
                slot
                for slot in base_slots
                if slot != "13:00-15:00"
            ]

        return self._slots_for_duration(base_slots, duration)

    def _online_slots_for_course(self, course_code: str) -> List[str]:
        course = self.courses.get(course_code, {"courseCode": course_code})
        return self._slots_for_duration(self.online_slots, self._course_lecture_duration(course))

    def _course_lecture_duration(self, course) -> int:
        code = self._course_code(course) or str(course or "").strip().upper()
        explicit = self._safe_int(
            course.get("lectureDurationMinutes") if isinstance(course, dict) else None,
            None,
        )
        if explicit:
            return max(1, explicit)
        return self.special_lecture_durations.get(code, DEFAULT_LECTURE_DURATION_MINUTES)

    def _course_section_duration(self, course) -> int:
        code = self._course_code(course) or str(course or "").strip().upper()
        explicit = self._safe_int(
            course.get("sectionDurationMinutes") if isinstance(course, dict) else None,
            None,
        )
        if explicit:
            return max(1, explicit)
        return self.special_section_durations.get(code, DEFAULT_SECTION_DURATION_MINUTES)

    def _slots_for_duration(self, slots: List[str], duration_minutes: int) -> List[str]:
        result = []
        duration = max(1, self._safe_int(duration_minutes, DEFAULT_LECTURE_DURATION_MINUTES))

        for slot in slots or []:
            parsed = self._slot_bounds(slot)
            if not parsed:
                continue

            start, end = parsed
            slot_length = end - start
            if duration >= slot_length:
                if duration == slot_length:
                    result.append(slot)
                continue

            current = start
            while current + duration <= end:
                result.append(f"{self._minutes_to_hhmm(current)}-{self._minutes_to_hhmm(current + duration)}")
                current += duration

        return list(dict.fromkeys(result))

    def _preferred_days_for_group(self, group_id: str) -> List[str]:
        used_days = {
            session["dayOfWeek"]
            for session in self.group_schedules.get(group_id, [])
        }

        return [
            day for day in self.days if day in used_days
        ] + [
            day for day in self.days if day not in used_days
        ]

    def _preferred_slots_for_group_on_day(
        self,
        group_id: str,
        day: str,
        slots: List[str],
    ) -> List[str]:
        slot_order = {slot: index for index, slot in enumerate(slots)}
        existing_indexes = sorted(
            slot_order[session["timeSlot"]]
            for session in self.group_schedules.get(group_id, [])
            if session["dayOfWeek"] == day and session["timeSlot"] in slot_order
        )

        if not existing_indexes:
            return list(slots)

        def score(slot: str) -> Tuple[int, int, str]:
            index = slot_order.get(slot, 999)

            if any(abs(index - current) == 1 for current in existing_indexes):
                return (0, min(abs(index - current) for current in existing_indexes), slot)

            return (1, min(abs(index - current) for current in existing_indexes), slot)

        return sorted(slots, key=score)

    def _section_difficulty(self, course: dict) -> int:
        lab_type = self._normalized_lab_type(course.get("labType"))

        if lab_type in {"PH101_LAB", "PH101_LA"}:
            return 95

        if lab_type == "LAB_ONLY":
            return 90

        return 80

    def _least_busy_instructors(self, instructors: List[dict]) -> List[dict]:
        return sorted(
            instructors,
            key=lambda item: (
                len(self.instructor_schedules.get(item["instructorId"], [])),
                item["instructorId"],
            ),
        )

    def _least_busy_instructors_for_course(
        self,
        instructors: List[dict],
        course_code: str,
    ) -> List[dict]:
        return sorted(
            instructors,
            key=lambda item: (
                sum(
                    1
                    for session in self.instructor_schedules.get(item["instructorId"], [])
                    if session.get("courseCode") == course_code
                    and session.get("sessionType") == "LECTURE"
                ),
                len(self.instructor_schedules.get(item["instructorId"], [])),
                item["instructorId"],
            ),
        )

    def _least_busy_rooms(self, rooms: List[dict]) -> List[dict]:
        return sorted(
            rooms,
            key=lambda item: (
                len(self.room_schedules.get(item["roomId"], [])),
                item["roomId"],
            ),
        )

    def _best_lecture_rooms(self, rooms: List[dict]) -> List[dict]:
        return sorted(
            rooms,
            key=lambda item: (
                -self._safe_int(item.get("capacity"), 0),
                len(self.room_schedules.get(item["roomId"], [])),
                item["roomId"],
            ),
        )

    def _assigned_course_codes(self, instructor: dict) -> set:
        return {
            self._course_code(item)
            for item in instructor.get("assignedCourses", [])
            if self._course_code(item)
        }

    def _course_category(self, course: dict) -> str:
        if course.get("isArabicOnline") is True:
            return "arabic"

        code = self._course_code(course)
        if code in self.arabic_online_courses:
            return "arabic"

        category = str(course.get("courseCategory") or "college").strip().lower()
        return "arabic" if category == "arabic" else "college"

    def _instructor_matches_course_category(self, instructor: dict, course: dict) -> bool:
        sources = set(instructor.get("sourceCategories") or [])

        if not sources or "all" in sources:
            return True

        return self._course_category(course) in sources

    def _normalize_assigned_courses(self, assigned_courses) -> List[dict]:
        if isinstance(assigned_courses, str):
            assigned_courses = [assigned_courses]

        result = []

        for item in assigned_courses or []:
            code = self._course_code(item)

            if code:
                result.append({"courseCode": code})

        return result

    def _course_code(self, item) -> Optional[str]:
        if isinstance(item, str):
            return item.strip().upper() or None

        if isinstance(item, dict):
            code = item.get("courseCode") or item.get("code")
            return str(code).strip().upper() if code else None

        return None

    def _normalized_person_name(self, value) -> str:
        if not value:
            return ""

        return "".join(str(value).strip().lower().split())

    def _course_level(self, course: dict) -> int:
        levels = self._normalize_levels(course)
        return levels[0] if levels else 1

    def _normalized_lab_type(self, value) -> Optional[str]:
        if value is None:
            return None

        lab_type = str(value).strip().upper()

        if lab_type in {"", "NONE", "NULL", "ONLINE"}:
            return None

        if lab_type in {"GENERAL", "LECTURE"}:
            return "GENERAL_LAB"

        if lab_type in {"LAB", "LABONLY"}:
            return "LAB_ONLY"

        if lab_type in {"PH101_LAB", "PH101_LA", "PHYSICS", "PHYSICS_LAB"}:
            return "PH101_LA"

        if lab_type == "PROJECT":
            return "PROJECT"

        if lab_type not in {"LAB_ONLY", "GENERAL_LAB", "PH101_LA", "PROJECT"}:
            return "GENERAL_LAB"

        return lab_type

    def _course_allows_general_section_rooms(self, course: dict) -> bool:
        truthy_fields = (
            "allowGeneralSectionRooms",
            "allowGeneralRoomsForSections",
            "sectionsInGeneralRooms",
            "canUseGeneralRoomsForSections",
        )
        for field in truthy_fields:
            if course.get(field) is True:
                return True

        room_type = str(
            course.get("sectionRoomType")
            or course.get("sectionRoom")
            or course.get("sectionVenueType")
            or ""
        ).strip().upper()
        if room_type in {"GENERAL", "LECTURE", "GENERAL_LAB"}:
            return True

        room_types = course.get("sectionRoomTypes") or course.get("allowedSectionRoomTypes")
        if isinstance(room_types, (list, tuple, set)):
            normalized = {
                str(item).strip().upper()
                for item in room_types
                if str(item).strip()
            }
            if normalized.intersection({"GENERAL", "LECTURE", "GENERAL_LAB"}):
                return True

        code = self._course_code(course)
        allowed_codes = (
            self.input_data.get("generalSectionCourses")
            or self.input_data.get("generalSectionRoomCourses")
            or self.input_data.get("coursesAllowedGeneralSections")
            or []
        )
        if isinstance(allowed_codes, str):
            allowed_codes = [allowed_codes]

        return code in {
            self._course_code(item)
            for item in allowed_codes
            if self._course_code(item)
        }

    def _create_student_groups_from_input(self) -> bool:
        raw_groups = self.input_data.get("studentGroups")

        if not isinstance(raw_groups, list) or not raw_groups:
            return False

        for index, item in enumerate(raw_groups, start=1):
            if not isinstance(item, dict):
                continue

            level = self._safe_int(item.get("level"), 1)
            if level <= 0:
                level = 1
            group_id = str(item.get("groupId") or f"L{level}G{index}").strip()
            group_id = self._normalize_group_id_level(group_id, level)
            if not group_id:
                continue

            course_codes = [
                code
                for code in (self._course_code(value) for value in item.get("courseCodes", []))
                if code
            ]

            student_count = self._safe_int(item.get("studentCount"), 0)
            self.group_sizes[group_id] = student_count
            departments = self._normalize_departments(item.get("departments"))
            if level <= 2:
                departments = []

            self.group_details[group_id] = {
                "groupId": group_id,
                "level": level,
                "studentCount": student_count,
                "department": None,
                "departments": departments,
                "courseCodes": course_codes,
                "cohortIds": [group_id],
            }

        return bool(self.group_details)

    def _normalize_group_id_level(self, group_id: str, level: int) -> str:
        import re

        if level <= 0:
            level = 1

        return re.sub(r"^L0(?=G)", f"L{level}", str(group_id).strip(), flags=re.IGNORECASE)

    def _create_student_groups_from_courses(self) -> bool:
        level_course_counts: Dict[int, Dict[str, int]] = defaultdict(dict)
        course_level_counts: Dict[str, Dict[int, int]] = {}

        for code, course in self.courses.items():
            if (
                self._is_online_course(course)
                or self._is_display_only_course(course)
                or self._is_project_course(course)
            ):
                continue

            level_counts = self._course_level_student_counts(course)
            total_students = sum(level_counts.values())
            if total_students <= 0:
                self.warnings.append(f"Skipped {code} groups because totalStudentCount is 0.")
                continue

            for level, count in level_counts.items():
                level_course_counts[level][code] = count
                course_level_counts.setdefault(code, {})[level] = count

        course_group_allocations = {
            code: self._allocate_course_group_counts_by_level(self.courses.get(code, {}), counts)
            for code, counts in course_level_counts.items()
        }

        for level, course_counts in sorted(level_course_counts.items()):
            max_students = max(course_counts.values(), default=0)
            if max_students <= 0:
                continue

            course_group_counts = {
                code: (
                    course_group_allocations[code].get(level, 0)
                    if code in course_group_allocations
                    else self._course_lecture_group_count(self.courses.get(code, {}), count)
                )
                for code, count in course_counts.items()
            }
            lecture_group_count = max(1, max(course_group_counts.values(), default=1))
            lecture_group_sizes = self._split_evenly(max_students, lecture_group_count)

            for group_index, group_size in enumerate(lecture_group_sizes, start=1):
                group_id = f"L{level}G{group_index}"
                section_ids = self._section_ids_for_group_size(group_id, group_size)

                self.group_sizes[group_id] = group_size
                self.group_details[group_id] = {
                    "groupId": group_id,
                    "level": level,
                    "studentCount": group_size,
                    "department": None,
                    "departments": [],
                    "courseCodes": [],
                    "sectionIds": section_ids,
                    "cohortIds": section_ids,
                }

            group_ids = [f"L{level}G{index}" for index in range(1, lecture_group_count + 1)]

            for code, student_count in sorted(course_counts.items()):
                course_group_count = course_group_counts.get(code, 1)
                if course_group_count <= 0:
                    continue

                course_group_count = min(course_group_count, lecture_group_count)
                course_sizes = self._split_evenly(student_count, course_group_count)
                selected_group_ids = self._select_course_group_ids_for_level(
                    group_ids,
                    code,
                    course_group_count,
                )

                for group_id, size in zip(selected_group_ids, course_sizes):
                    if size <= 0:
                        continue

                    self.course_group_sizes[code][group_id] = size
                    section_ids = self._section_ids_for_group_size(group_id, size)
                    current_section_ids = self.group_details[group_id].get("sectionIds") or []
                    if len(section_ids) > len(current_section_ids):
                        self.group_details[group_id]["sectionIds"] = section_ids
                        self.group_details[group_id]["cohortIds"] = section_ids

                    course_codes = self.group_details[group_id]["courseCodes"]
                    if code not in course_codes:
                        course_codes.append(code)

        return bool(self.group_details)

    def _select_course_group_ids_for_level(
        self,
        group_ids: List[str],
        course_code: str,
        count: int,
    ) -> List[str]:
        if count >= len(group_ids):
            return list(group_ids)

        ranked = sorted(
            group_ids,
            key=lambda group_id: (
                len(self.group_details.get(group_id, {}).get("courseCodes") or []),
                (sum(ord(ch) for ch in course_code) + self._group_sort_key(group_id)[1]) % max(1, len(group_ids)),
                self._group_sort_key(group_id),
            ),
        )

        return sorted(ranked[:count], key=self._group_sort_key)

    def _assign_generated_cohorts_to_groups(self) -> None:
        course_segment_groups = defaultdict(list)
        segment_max_groups = defaultdict(int)

        for group_id, details in self.group_details.items():
            if details.get("cohortIds"):
                continue

            course_codes = list(details.get("courseCodes") or [])
            if len(course_codes) != 1:
                details["cohortIds"] = [group_id]
                continue

            course_code = course_codes[0]
            for segment in self._group_cohort_segments(details):
                key = (course_code, segment)
                course_segment_groups[key].append(group_id)

        for (_course_code, segment), group_ids in course_segment_groups.items():
            segment_max_groups[segment] = max(segment_max_groups[segment], len(group_ids))

        for (_course_code, segment), group_ids in course_segment_groups.items():
            ordered_group_ids = sorted(group_ids, key=self._group_sort_key)
            max_count = max(1, segment_max_groups[segment])
            group_count = max(1, len(ordered_group_ids))

            for index, group_id in enumerate(ordered_group_ids):
                cohort_ids = self._cohort_ids_for_group_segment(segment, max_count, group_count, index)
                existing = set(self.group_details[group_id].get("cohortIds") or [])
                existing.update(cohort_ids)
                self.group_details[group_id]["cohortIds"] = sorted(existing)

    def _group_cohort_segments(self, details: dict) -> List[Tuple[int, str]]:
        level = self._safe_int(details.get("level"), 1)
        departments = self._normalize_departments(details.get("departments"))

        if level <= 2 or not departments:
            departments = ["SHARED"]

        return [(level, department) for department in departments]

    def _cohort_ids_for_group_segment(
        self,
        segment: Tuple[int, str],
        max_count: int,
        group_count: int,
        group_index: int,
    ) -> List[str]:
        start = math.floor(group_index * max_count / group_count) + 1
        end = math.floor((group_index + 1) * max_count / group_count)
        return [
            self._cohort_id(segment, index)
            for index in range(start, max(start, end) + 1)
        ]

    def _cohort_id(self, segment: Tuple[int, str], index: int) -> str:
        level, department = segment
        clean_department = "".join(ch for ch in str(department).upper() if ch.isalnum()) or "SHARED"
        return f"L{level}{clean_department}C{index}"

    def _target_group_ids_for_course(self, code: str, course: dict) -> List[str]:
        explicit = [
            group_id
            for group_id, details in self.group_details.items()
            if code in set(details.get("courseCodes") or [])
        ]

        if explicit:
            return explicit

        levels = set(self._normalize_levels(course))
        departments = set(self._normalize_departments(course.get("departments")))

        result = []
        for group_id, details in self.group_details.items():
            if details.get("isProjectGroup"):
                continue

            if details.get("level") not in levels:
                continue

            group_departments = set(self._normalize_departments(details.get("departments")))
            if departments and group_departments and not departments.intersection(group_departments):
                continue

            result.append(group_id)

        return result

    def _project_group_ids_for_course(self, code: str, course: dict) -> List[str]:
        levels = self._project_levels(course)
        return [
            self._project_group_id(level, code)
            for level in levels
            if self._project_group_id(level, code) in self.group_details
        ]

    def _project_levels(self, course: dict) -> List[int]:
        if self._is_project_course(course):
            return [self.project_default_level]

        levels = self._normalize_levels(course)
        return levels or [self.project_default_level]

    def _project_student_count(self, course: dict, level: int) -> int:
        total = self._safe_int(course.get("totalStudentCount"), 0)
        if total > 0:
            return total

        breakdown_total = sum(
            self._safe_int(row.get("studentCount"), 0)
            for row in self._normalize_student_breakdown(course.get("studentBreakdown"))
            if self._safe_int(row.get("level"), None) == level
        )
        if breakdown_total > 0:
            return breakdown_total

        return sum(
            self._safe_int(details.get("studentCount"), 0)
            for details in self.group_details.values()
            if not details.get("isProjectGroup")
            and self._safe_int(details.get("level"), None) == level
        )

    def _project_group_id(self, level: int, code: str) -> str:
        clean_code = "".join(ch for ch in code if ch.isalnum())
        return f"L{level}PROJECT{clean_code}"

    def _ensure_online_group_for_course(self, code: str, course: dict) -> List[str]:
        group_ids = []

        for level in self._normalize_levels(course):
            clean_code = "".join(ch for ch in code if ch.isalnum())
            group_id = f"L{level}ONLINE{clean_code}"
            group_ids.append(group_id)

            if group_id in self.group_details:
                continue

            total = self._safe_int(course.get("totalStudentCount"), 0)
            if total <= 0:
                total = self._safe_int(course.get("enrollmentCount"), 0)

            self.group_sizes[group_id] = total
            self.group_details[group_id] = {
                "groupId": group_id,
                "level": level,
                "studentCount": total,
                "department": None,
                "departments": self._normalize_departments(course.get("departments")),
                "courseCodes": [code],
                "isOnlineGroup": True,
            }

        return group_ids

    def _ensure_arabic_online_group_for_course(self, code: str, course: dict) -> List[str]:
        level = self._normalize_levels(course)[0]
        clean_code = "".join(ch for ch in code if ch.isalnum())
        group_id = f"L{level}ARABIC{clean_code}"

        if group_id not in self.group_details:
            total = self._safe_int(course.get("totalStudentCount"), 0)
            if total <= 0:
                total = self._safe_int(course.get("enrollmentCount"), 0)

            self.group_sizes[group_id] = total
            self.group_details[group_id] = {
                "groupId": group_id,
                "level": level,
                "studentCount": total,
                "department": None,
                "departments": self._normalize_departments(course.get("departments")),
                "courseCodes": [code],
                "isArabicOnlineGroup": True,
                "isOnlineGroup": True,
            }

        return [group_id]

    def _matching_level_student_count(self, level: int, departments: List[str]) -> int:
        department_set = set(departments)
        total = 0

        for details in self.group_details.values():
            if details.get("isProjectGroup"):
                continue

            if details.get("level") != level:
                continue

            group_departments = set(self._normalize_departments(details.get("departments")))
            if department_set and group_departments and not department_set.intersection(group_departments):
                continue

            total += self._safe_int(details.get("studentCount"), 0)

        return total

    def _course_level_student_counts(self, course: dict) -> Dict[int, int]:
        levels = self._normalize_levels(course)
        breakdown = self._normalize_student_breakdown(course.get("studentBreakdown"))
        counts = {level: 0 for level in levels}

        for row in breakdown:
            level = self._safe_int(row.get("level"), None)
            if level in counts:
                counts[level] += self._safe_int(row.get("studentCount"), 0)

        if any(counts.values()):
            return {level: count for level, count in counts.items() if count > 0}

        total = self._safe_int(course.get("totalStudentCount"), 0)
        if total <= 0:
            return {}

        sizes = self._split_evenly(total, len(levels))
        return {
            level: size
            for level, size in zip(levels, sizes)
            if size > 0
        }

    def _course_departments_for_level(self, course: dict, level: int) -> List[str]:
        departments = {
            row.get("department")
            for row in self._normalize_student_breakdown(course.get("studentBreakdown"))
            if self._safe_int(row.get("level"), None) == level
            and row.get("department")
            and str(row.get("department")).strip().upper() != "SHARED"
        }

        if departments:
            return sorted(str(value).strip().upper() for value in departments)

        course_departments = self._normalize_departments(course.get("departments"))
        if course_departments == ["SHARED"]:
            return ["SHARED"]

        return course_departments

    def _arabic_day_and_slot(self, course: dict, course_index: int) -> Tuple[str, str]:
        day = course.get("dayOfWeek") or course.get("day")
        if not day:
            day = self.days[course_index % len(self.days)]

        slot = self.online_slots[0] if self.online_slots else "17:00-19:00"
        return str(day), str(slot)

    def _arabic_instructor_for_course(self, course: dict) -> Optional[dict]:
        instructor_ids = set(course.get("instructorIds") or [])

        if course.get("instructorId") is not None:
            instructor_ids.add(self._safe_int(course.get("instructorId"), None))

        for instructor_id in instructor_ids:
            instructor = self.instructors.get(instructor_id)
            if (
                instructor
                and instructor.get("instructorType") == "DOCTOR"
                and self._instructor_matches_course_category(instructor, course)
            ):
                return instructor

        code = self._course_code(course)
        for instructor in self.instructors.values():
            if (
                instructor.get("instructorType") == "DOCTOR"
                and self._instructor_matches_course_category(instructor, course)
                and code in self._assigned_course_codes(instructor)
            ):
                return instructor

        return None

    def _merge_passthrough_course_fields(self, session: dict, course: dict) -> dict:
        for key, value in course.items():
            if key in session:
                continue

            if key in {"labType", "scheduleMode", "isArabicOnline"}:
                continue

            if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                session[key] = value

        return session

    def _project_day_and_slot(self, course: dict) -> Tuple[str, str]:
        day = course.get("dayOfWeek") or course.get("day") or self.days[0]
        slot = "17:00-19:00"
        return str(day), str(slot)

    def _project_details(self, course: dict) -> dict:
        code = self._course_code(course)
        defaults = self.project_display_details.get(code, {})
        doctor = self._project_instructor_for_course(course, "DOCTOR")
        assistant = self._project_instructor_for_course(course, "TA")
        doctor_id = (
            self._safe_int(course.get("doctorId"), None)
            or self._safe_int(course.get("instructorId"), None)
            or (doctor.get("instructorId") if doctor else None)
        )
        assistant_id = (
            self._safe_int(course.get("assistantId"), None)
            or self._safe_int(course.get("taId"), None)
            or (assistant.get("instructorId") if assistant else None)
        )

        return {
            **defaults,
            "doctorId": doctor_id,
            "assistantId": assistant_id,
            "doctorName": (
                course.get("doctorName")
                or course.get("instructorName")
                or defaults.get("doctorName")
                or (doctor.get("name") if doctor else None)
            ),
            "assistantName": (
                course.get("assistantName")
                or course.get("taName")
                or defaults.get("assistantName")
                or (assistant.get("name") if assistant else None)
            ),
            "timeSlot": course.get("timeSlot") or defaults.get("timeSlot"),
            "lectureRoomNumber": (
                course.get("lectureRoomNumber")
                or course.get("roomNumber")
                or defaults.get("lectureRoomNumber")
            ),
            "sectionRoomNumber": (
                course.get("sectionRoomNumber")
                or defaults.get("sectionRoomNumber")
            ),
        }

    def _project_instructor_for_course(self, course: dict, instructor_type: str) -> Optional[dict]:
        code = self._course_code(course)
        instructor_ids = [
            self._safe_int(value, None)
            for value in course.get("instructorIds") or []
        ]

        for instructor_id in instructor_ids:
            instructor = self.instructors.get(instructor_id)
            if instructor and instructor.get("instructorType") == instructor_type:
                return instructor

        for instructor in self.instructors.values():
            if (
                instructor.get("instructorType") == instructor_type
                and self._instructor_matches_course_category(instructor, course)
                and code in self._assigned_course_codes(instructor)
            ):
                return instructor

        return None

    def _project_instructors_for_course(self, course: dict) -> List[dict]:
        code = self._course_code(course)
        result = []
        seen = set()

        for value in course.get("instructorIds") or []:
            instructor_id = self._safe_int(value, None)
            if instructor_id is None or instructor_id in seen:
                continue

            instructor = self.instructors.get(instructor_id)
            if not instructor:
                self.warnings.append(
                    f"Project instructor id={instructor_id} for {code} was not found in instructors."
                )
                continue

            result.append(instructor)
            seen.add(instructor_id)

        if result:
            return result

        for instructor_type in ("DOCTOR", "TA"):
            instructor = self._project_instructor_for_course(course, instructor_type)
            if instructor and instructor.get("instructorId") not in seen:
                result.append(instructor)
                seen.add(instructor.get("instructorId"))

        return result

    def _course_difficulty(self, course: dict, is_online: bool) -> int:
        if is_online:
            return 30

        levels = self._normalize_levels(course)
        departments = self._normalize_departments(course.get("departments"))
        score = 100

        if len(levels) > 1:
            score += 30

        if len(departments) > 1:
            score += 30

        return score

    def _normalize_levels(self, item: dict) -> List[int]:
        raw_levels = item.get("levels")

        if raw_levels is None:
            raw_levels = item.get("level", item.get("academicLevel", 1))

        if isinstance(raw_levels, (list, tuple, set)):
            levels = [
                self._safe_int(value, None)
                for value in raw_levels
            ]
        else:
            levels = [self._safe_int(raw_levels, None)]

        result = sorted({level for level in levels if level is not None and level > 0})
        return result or [1]

    def _normalize_departments(self, value) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = []

        return sorted({
            str(item).strip().upper()
            for item in values
            if str(item).strip()
        })

    def _normalize_student_breakdown(self, value) -> List[dict]:
        if not isinstance(value, list):
            return []

        result = []
        for item in value:
            if not isinstance(item, dict):
                continue

            level = self._safe_int(item.get("level"), 1)
            if level <= 0:
                level = 1

            result.append({
                "level": level,
                "department": (
                    str(item.get("department")).strip().upper()
                    if item.get("department") is not None else None
                ),
                "studentCount": self._safe_int(item.get("studentCount"), 0),
            })

        return result

    def _course_student_count(self, item: dict) -> int:
        explicit = self._safe_int(
            item.get("totalStudentCount", item.get("enrollmentCount")),
            None,
        )

        if explicit is not None:
            return explicit

        breakdown = self._normalize_student_breakdown(item.get("studentBreakdown"))
        return sum(row["studentCount"] for row in breakdown)

    def _extract_course_instructor_ids(self, item: dict) -> List[int]:
        values = []

        raw_ids = item.get("instructorIds", [])
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]

        values.extend(raw_ids)

        instructor_name = item.get("instructorName")
        if instructor_name is not None:
            values.append(instructor_name)

        result = sorted({
            self._safe_int(value, None)
            for value in values
            if self._safe_int(value, None) is not None
        })

        return result

    def _merge_course_records(self, current: dict, incoming: dict) -> dict:
        merged = dict(current)
        merged["levels"] = sorted(set(current.get("levels", [])) | set(incoming.get("levels", [])))
        merged["level"] = merged["levels"][0]
        merged["academicLevel"] = merged["levels"][0]
        merged["departments"] = sorted(set(current.get("departments", [])) | set(incoming.get("departments", [])))
        merged["instructorIds"] = sorted(set(current.get("instructorIds", [])) | set(incoming.get("instructorIds", [])))
        merged["studentBreakdown"] = current.get("studentBreakdown", []) or incoming.get("studentBreakdown", [])
        merged["totalStudentCount"] = max(
            self._safe_int(current.get("totalStudentCount"), 0),
            self._safe_int(incoming.get("totalStudentCount"), 0),
        )
        merged["enrollmentCount"] = merged["totalStudentCount"]
        merged["labType"] = current.get("labType") or incoming.get("labType")
        merged["isArabicOnline"] = current.get("isArabicOnline") or incoming.get("isArabicOnline")
        merged["courseCategory"] = (
            "arabic"
            if current.get("courseCategory") == "arabic" or incoming.get("courseCategory") == "arabic"
            else "college"
        )
        merged["lectureDurationMinutes"] = (
            current.get("lectureDurationMinutes") or incoming.get("lectureDurationMinutes")
        )
        merged["sectionDurationMinutes"] = (
            current.get("sectionDurationMinutes") or incoming.get("sectionDurationMinutes")
        )
        return merged

    def _group_sort_key(self, group_id: str):
        import re

        project_match = re.search(r"L(\d+)PROJECT", group_id.upper())
        if project_match:
            level = int(project_match.group(1))
            return (level, 999, "PROJECT", group_id)

        match = re.search(r"L(\d+).*?G(\d+)([A-Z]*)", group_id.upper())
        if not match:
            return (999, 999, "", group_id)

        level = int(match.group(1))
        group_number = int(match.group(2))
        suffix = match.group(3) or ""
        return (level, group_number, suffix, group_id)

    def _generated_group_id(self, level: int, index: int) -> str:
        letters_per_group = max(
            1,
            math.ceil(self.max_lecture_group_size / max(1, self.max_section_size)),
        )
        group_number = math.ceil(index / letters_per_group)
        letter_index = (index - 1) % letters_per_group
        suffix = chr(ord("A") + letter_index)
        return f"L{level}G{group_number}{suffix}"

    def _has_group_time_conflict(
        self,
        group_id: str,
        day: str,
        slot: str,
        candidate: Optional[dict] = None,
    ) -> bool:
        for session in self.group_schedules.get(group_id, []):
            if session.get("dayOfWeek") != day:
                continue

            if not self._slots_overlap(session.get("timeSlot"), slot):
                continue

            if candidate and self._sessions_can_overlap(session, candidate):
                continue

            if self._same_group_sessions_conflict(session, candidate):
                return True

        if candidate and candidate.get("isRecordedOnline"):
            return False

        for cohort_id in self._cohort_ids_for_candidate(group_id, candidate):
            if self._has_cohort_time_conflict(cohort_id, day, slot, candidate):
                return True

        return False

    def _same_group_sessions_conflict(
        self,
        existing: dict,
        candidate: Optional[dict],
    ) -> bool:
        if not candidate:
            return True

        existing_section = existing.get("sectionId")
        candidate_section = candidate.get("sectionId")

        if existing_section and candidate_section and existing_section != candidate_section:
            return False

        return True

    def _cohort_ids_for_candidate(
        self,
        group_id: str,
        candidate: Optional[dict],
    ) -> List[str]:
        if candidate and (
            candidate.get("isRecordedOnline")
            or (
                candidate.get("isOnline")
                and candidate.get("courseCode") in self.online_recorded_courses
            )
        ):
            return []

        if candidate and candidate.get("sectionId"):
            return [candidate["sectionId"]]

        details = self.group_details.get(group_id, {})
        return list(details.get("sectionIds") or details.get("cohortIds") or [group_id])

    def _cohort_ids_for_session(self, session: dict) -> List[str]:
        return self._cohort_ids_for_candidate(session.get("groupId"), session)

    def _has_cohort_time_conflict(
        self,
        cohort_id: str,
        day: str,
        slot: str,
        candidate: Optional[dict] = None,
    ) -> bool:
        for existing_group_id, sessions in self.group_schedules.items():
            if cohort_id not in self.group_details.get(existing_group_id, {}).get("cohortIds", []):
                continue

            for session in sessions:
                if cohort_id not in self._cohort_ids_for_session(session):
                    continue

                if session.get("dayOfWeek") != day:
                    continue

                if not self._slots_overlap(session.get("timeSlot"), slot):
                    continue

                if candidate and self._sessions_can_overlap(session, candidate):
                    continue

                return True

        return False

    def _has_instructor_time_conflict(self, instructor_id: int, day: str, slot: str) -> bool:
        for session in self.instructor_schedules.get(instructor_id, []):
            if session.get("isRecordedOnline"):
                continue
            if session.get("dayOfWeek") == day and self._slots_overlap(session.get("timeSlot"), slot):
                return True
        return False

    def _has_room_time_conflict(self, room_id: int, day: str, slot: str) -> bool:
        for session in self.room_schedules.get(room_id, []):
            if session.get("dayOfWeek") == day and self._slots_overlap(session.get("timeSlot"), slot):
                return True
        return False

    def _sessions_can_overlap(self, first: dict, second: dict) -> bool:
        first_project = first.get("isProject") is True or first.get("sessionType") == "PROJECT"
        second_project = second.get("isProject") is True or second.get("sessionType") == "PROJECT"

        if first_project and second_project:
            return True

        return (
            first_project and self._is_arabic_online_session(second)
        ) or (
            second_project and self._is_arabic_online_session(first)
        )

    def _is_arabic_online_session(self, session: dict) -> bool:
        return (
            session.get("isArabicOnline") is True
            or (
                session.get("isOnline") is True
                and str(session.get("courseCode") or "").strip().upper() in self.arabic_online_courses
            )
        )

    def _slot_bounds(self, slot: str) -> Optional[Tuple[int, int]]:
        if not isinstance(slot, str) or "-" not in slot:
            return None

        start_text, end_text = slot.split("-", 1)
        start = self._time_to_minutes(start_text)
        end = self._time_to_minutes(end_text)

        if start is None or end is None or end <= start:
            return None

        return start, end

    def _slots_overlap(self, first: str, second: str) -> bool:
        first_bounds = self._slot_bounds(first)
        second_bounds = self._slot_bounds(second)

        if not first_bounds or not second_bounds:
            return first == second

        first_start, first_end = first_bounds
        second_start, second_end = second_bounds
        return first_start < second_end and second_start < first_end

    def _time_to_minutes(self, value) -> Optional[int]:
        text = self._norm_hhmm(value)
        if ":" not in text:
            return None

        hour_text, minute_text = text.split(":", 1)
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError:
            return None

        if hour < 0 or minute < 0 or minute >= 60:
            return None

        return (hour % 24) * 60 + minute

    def _minutes_to_hhmm(self, minutes: int) -> str:
        minutes = minutes % (24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _section_label(self, group_id: str, index: int) -> str:
        if index <= 0:
            index = 1

        letters = []
        value = index
        while value:
            value -= 1
            letters.append(chr(ord("A") + (value % 26)))
            value //= 26

        return f"{group_id}{''.join(reversed(letters))}"

    def _sort_sessions(self, sessions: List[dict]) -> List[dict]:
        day_order = {
            day: index
            for index, day in enumerate(self.days)
        }

        return sorted(
            sessions,
            key=lambda item: (
                day_order.get(item["dayOfWeek"], 999),
                item["timeSlot"],
                item["courseCode"],
                item.get("sectionId") or "",
            ),
        )

    def _sort_aptech_sessions(self, sessions: List[dict]) -> List[dict]:
        day_order = {
            day: index
            for index, day in enumerate(self.days)
        }

        return sorted(
            sessions,
            key=lambda item: (
                self._safe_int(item.get("level"), 999),
                day_order.get(item.get("dayOfWeek"), 999),
                item.get("timeSlot") or "",
                item.get("courseCode") or "",
                item.get("instructorName") or "",
            ),
        )

    def _course_output_sort_key(self, item: dict):
        code = item.get("courseCode") or ""
        course = self.courses.get(code, item)
        is_project = self._is_project_course(course)
        levels = (
            item.get("levels")
            if isinstance(item.get("levels"), list) and item.get("levels")
            else self._normalize_levels(course)
        )
        primary_level = min(
            [self._safe_int(level, 999) for level in levels]
            or [999]
        )

        return (
            1 if is_project else 0,
            primary_level,
            str(code),
            str(item.get("courseName") or ""),
        )

    def _add_unscheduled(self, demand: dict, reason: str) -> bool:
        demand["_reason_added"] = True
        self.unscheduled_reasons.append(reason)
        return False

    def _norm_hhmm(self, value) -> str:
        return str(value or "")[:5]

    def _safe_int(self, value, default=0):
        try:
            if value is None:
                return default

            return int(value)

        except (TypeError, ValueError):
            return default

    def _normalize_code(self, value) -> Optional[str]:
        code = str(value or "").strip().upper()
        return code or None

    def _codes_from_course_items(self, items) -> set:
        codes = set()

        if isinstance(items, (str, int)):
            code = self._normalize_code(items)
            return {code} if code else set()

        if isinstance(items, dict):
            course_code = self._normalize_code(items.get("courseCode") or items.get("code"))
            if course_code:
                codes.add(course_code)
                return codes

            for key in items:
                code = self._normalize_code(key)
                if code:
                    codes.add(code)
            return codes

        for item in items or []:
            if isinstance(item, dict):
                code = self._normalize_code(item.get("courseCode") or item.get("code"))
            else:
                code = self._normalize_code(item)

            if code:
                codes.add(code)

        return codes

    def _code_set_setting(self, keys: Iterable[str], default: Iterable[str]) -> set:
        result = {
            code
            for code in (self._normalize_code(item) for item in default or [])
            if code
        }

        for key in keys:
            result.update(self._codes_from_course_items(self.input_data.get(key)))

        return result

    def _text_set_setting(self, keys: Iterable[str], default: Iterable[str]) -> set:
        result = {str(item).strip().upper() for item in default or [] if str(item).strip()}

        for key in keys:
            value = self.input_data.get(key)
            if isinstance(value, dict):
                result.update(str(item).strip().upper() for item in value if str(item).strip())
            elif isinstance(value, (str, int)):
                text = str(value).strip().upper()
                if text:
                    result.add(text)
            else:
                result.update(str(item).strip().upper() for item in value or [] if str(item).strip())

        return result

    def _int_set_setting(self, keys: Iterable[str], default: Iterable[int]) -> set:
        result = {self._safe_int(item, None) for item in default or []}
        result.discard(None)

        for key in keys:
            value = self.input_data.get(key)
            if isinstance(value, dict):
                items = value.keys()
            elif isinstance(value, (str, int)):
                items = [value]
            else:
                items = value or []
            for item in items:
                parsed = self._safe_int(item, None)
                if parsed is not None:
                    result.add(parsed)

        return result

    def _int_dict_setting(self, keys: Iterable[str], default: Dict) -> dict:
        result = {
            str(key).strip().upper(): self._safe_int(value, 0)
            for key, value in (default or {}).items()
            if str(key).strip()
        }

        for key in keys:
            value = self.input_data.get(key)
            if not isinstance(value, dict):
                continue

            for item_key, item_value in value.items():
                normalized_key = str(item_key).strip().upper()
                if normalized_key:
                    result[normalized_key] = self._safe_int(item_value, 0)

        return result

    def _text_dict_setting(self, keys: Iterable[str], default: Dict) -> dict:
        result = {
            str(key).strip().upper(): str(value).strip().upper()
            for key, value in (default or {}).items()
            if str(key).strip() and str(value).strip()
        }

        for key in keys:
            value = self.input_data.get(key)
            if not isinstance(value, dict):
                continue

            for item_key, item_value in value.items():
                normalized_key = str(item_key).strip().upper()
                normalized_value = str(item_value).strip().upper()
                if normalized_key and normalized_value:
                    result[normalized_key] = normalized_value

        return result

    def _project_display_details_setting(self) -> dict:
        details = {
            self._normalize_code(code): dict(value)
            for code, value in PROJECT_DISPLAY_DETAILS.items()
            if self._normalize_code(code) and isinstance(value, dict)
        }

        configured = self.input_data.get("projectDisplayDetails") or self.input_data.get("projectDetails")
        if isinstance(configured, dict):
            for code, value in configured.items():
                normalized_code = self._normalize_code(code)
                if normalized_code and isinstance(value, dict):
                    details[normalized_code] = {
                        **details.get(normalized_code, {}),
                        **value,
                    }

        for item in self.input_data.get("projectCourses") or []:
            if not isinstance(item, dict):
                continue

            code = self._normalize_code(item.get("courseCode") or item.get("code"))
            if not code:
                continue

            passthrough = {
                key: value
                for key, value in item.items()
                if key
                in {
                    "dayOfWeek",
                    "day",
                    "timeSlot",
                    "doctorId",
                    "doctorName",
                    "assistantId",
                    "assistantName",
                    "taId",
                    "taName",
                    "lectureRoomNumber",
                    "sectionRoomNumber",
                }
            }
            details[code] = {**details.get(code, {}), **passthrough}

        return details

    def _list_or_default(self, value, default: List[str]) -> List[str]:
        return list(value) if isinstance(value, list) and value else list(default)

    def _empty_fail(self, message: str) -> dict:
        aptech_output = (
            self._build_aptech_courses_output()
            if hasattr(self, "aptech_courses")
            else []
        )

        return {
            "success": False,
            "message": message,
            "scheduleUrl": self.input_data.get("scheduleUrl") or self.input_data.get("outputScheduleUrl"),

            "courseTable": {"levels": []},

            "collegeCourses": [],
            "arabicCourses": [],
            "aptechCourses": aptech_output,

            "schedulesByType": {
                "college": [],
                "arabic": [],
                "aptech": aptech_output,
            },

            "optimizationSummary": {
                "averageCampusDaysPerGroup": 0,
                "totalGaps": 0,
                "totalSingleSessionDays": 0,
                "groups": [],
            },

            "groupSchedules": [],
            "studentGroupSchedules": [],
            "instructorSchedules": [],
            "roomSchedules": [],

            "totalSessions": 0,
            "totalGroups": 0,
            "totalStudentGroups": 0,

            "metadata": {
                "unscheduledCount": 1 + len(getattr(self, "skipped_courses", {})),
                "unscheduledReasons": [message],
                "warnings": getattr(self, "warnings", []),
                "capacityIssues": [],
                "conflicts": [],
                "unscheduledAptechCourses": [
                    course for course in aptech_output if course.get("status") != "SCHEDULED"
                ],
                "skippedCourses": [
                    {"courseCode": code, "reason": reason}
                    for code, reason in sorted(getattr(self, "skipped_courses", {}).items())
                ],
            },
        }
