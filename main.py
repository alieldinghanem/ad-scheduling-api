import json
import sys
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any, Dict, List

from scheduler import (
    DEFAULT_DAYS,
    DEFAULT_ONLINE_SLOTS,
    DEFAULT_REGULAR_SLOTS,
    IGNORED_ONLINE_COURSES,
    SchedulingEngine,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


LOCAL_INPUT_FILE = "backend_input.json"
OUTPUT_FILE = "output_schedule.json"
DEFAULT_ONLINE_COURSES = ["REM101", "MGT101", "HUM101", "ETS401"]
DEFAULT_LECTURE_DURATION_MINUTES = 120
DEFAULT_SECTION_DURATION_MINUTES = 120
SPECIAL_LECTURE_DURATIONS = {"CS214": 60, "ETS401": 60}
SPECIAL_SECTION_DURATIONS = {"CS214": 60}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_course(
    raw: Dict[str, Any],
    force_online: bool = False,
    force_arabic_online: bool | None = None,
    force_aptech: bool = False,
) -> Dict[str, Any]:
    code = str(raw.get("courseCode") or raw.get("code") or "").strip().upper()
    if not code:
        raise ValueError("Course is missing courseCode")

    lab_type = raw.get("labType")
    if force_online or code in DEFAULT_ONLINE_COURSES:
        lab_type = None

    levels = raw.get("levels")
    if levels is None:
        levels = [safe_int(raw.get("level", raw.get("academicLevel", 1)), 1)]

    if not isinstance(levels, list):
        levels = [levels]

    departments = raw.get("departments")
    if departments is None:
        departments = []

    if not isinstance(departments, list):
        departments = [departments]

    is_arabic_online = bool(raw.get("isArabicOnline") or code in DEFAULT_ONLINE_COURSES)
    if force_arabic_online is not None:
        is_arabic_online = force_arabic_online

    is_online = bool(raw.get("isOnline") or force_online or is_arabic_online)

    return {
        **raw,
        "courseCode": code,
        "courseName": raw.get("courseName") or code,
        "levels": [safe_int(value, 1) for value in levels],
        "departments": [
            str(value).strip().upper()
            for value in departments
            if str(value).strip()
        ],
        "level": safe_int(raw.get("level", raw.get("academicLevel", 1)), 1),
        "academicLevel": safe_int(raw.get("academicLevel", raw.get("level", 1)), 1),
        "enrollmentCount": safe_int(
            raw.get("enrollmentCount", raw.get("totalStudentCount")),
            0,
        ),
        "totalStudentCount": safe_int(
            raw.get("totalStudentCount", raw.get("enrollmentCount")),
            0,
        ),
        "studentBreakdown": raw.get("studentBreakdown") if isinstance(raw.get("studentBreakdown"), list) else [],
        "instructorIds": raw.get("instructorIds") if isinstance(raw.get("instructorIds"), list) else [],
        "labType": lab_type,
        "isOnline": is_online,
        "isArabicOnline": is_arabic_online,
        "isAptech": bool(raw.get("isAptech") or force_aptech),
        "lectureDurationMinutes": safe_int(
            raw.get("lectureDurationMinutes"),
            SPECIAL_LECTURE_DURATIONS.get(code, DEFAULT_LECTURE_DURATION_MINUTES),
        ),
        "sectionDurationMinutes": safe_int(
            raw.get("sectionDurationMinutes"),
            SPECIAL_SECTION_DURATIONS.get(code, DEFAULT_SECTION_DURATION_MINUTES),
        ),
    }


def normalize_instructor(raw: Dict[str, Any]) -> Dict[str, Any]:
    instructor_id = safe_int(raw.get("instructorId"), None)
    if instructor_id is None:
        raise ValueError("Instructor is missing instructorId")

    assigned = raw.get("assignedCourses", [])
    if isinstance(assigned, str):
        assigned = [assigned]

    assigned_courses = []
    for item in assigned or []:
        if isinstance(item, str):
            code = item.strip().upper()
        elif isinstance(item, dict):
            code = str(item.get("courseCode") or item.get("code") or "").strip().upper()
        else:
            code = ""

        if code:
            assigned_courses.append({"courseCode": code})

    instructor_type = str(raw.get("instructorType") or "DOCTOR").strip().upper()
    if instructor_type in {"TECHNICAL ASSISTANT", "TECHNICAL_ASSISTANT", "ASSISTANT"}:
        instructor_type = "TA"

    if instructor_type not in {"DOCTOR", "TA", "APTECH"}:
        instructor_type = "DOCTOR"

    return {
        **raw,
        "instructorId": instructor_id,
        "name": raw.get("name") or f"Instructor {instructor_id}",
        "instructorType": instructor_type,
        "assignedCourses": assigned_courses,
        "availabilities": raw.get("availabilities") if isinstance(raw.get("availabilities"), list) else [],
    }


def normalize_room(raw: Dict[str, Any]) -> Dict[str, Any]:
    room_id = safe_int(raw.get("roomId"), None)
    if room_id is None:
        raise ValueError("Room is missing roomId")

    room_type = str(raw.get("roomType") or "GENERAL").strip().upper()
    if room_type in {"LECTURE", "LECTURE_HALL", "GENERAL_LAB"}:
        room_type = "GENERAL"
    elif room_type == "LAB":
        room_type = "LAB_ONLY"
    elif room_type in {"PHYSICS", "PHYSICS_LAB", "PH101_LAB"}:
        room_type = "PH101_LA"

    return {
        **raw,
        "roomId": room_id,
        "roomNumber": str(raw.get("roomNumber") or room_id),
        "roomType": room_type,
        "capacity": safe_int(raw.get("capacity"), 0),
    }


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Scheduling input must be a JSON object")

    container = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    courses: List[Dict[str, Any]] = []

    for raw in container.get("courses") or []:
        if isinstance(raw, dict):
            courses.append(normalize_course(raw))

    for raw in container.get("regularCourses") or []:
        if isinstance(raw, dict):
            courses.append(normalize_course(raw))

    for raw in container.get("onlineCourses") or []:
        if isinstance(raw, dict):
            code = str(raw.get("courseCode") or "").strip().upper()
            if code in DEFAULT_ONLINE_COURSES and code not in IGNORED_ONLINE_COURSES:
                courses.append(normalize_course(raw, force_online=True))

    arabic_courses = [
        normalize_course(raw, force_online=True, force_arabic_online=True)
        for raw in container.get("arabicCourses", [])
        if isinstance(raw, dict)
    ]

    regular_instructors = [
        normalize_instructor(raw)
        for raw in (
            list(container.get("instructors", []))
            + list(container.get("regularInstructors", []))
        )
        if isinstance(raw, dict)
    ]

    arabic_instructors = [
        normalize_instructor(raw)
        for raw in container.get("arabicInstructors", [])
        if isinstance(raw, dict)
    ]

    aptech_instructors = [
        normalize_instructor(raw)
        for raw in container.get("aptechInstructors", [])
        if isinstance(raw, dict)
    ]

    rooms = [
        normalize_room(raw)
        for raw in container.get("rooms", [])
        if isinstance(raw, dict)
    ]

    online_course_codes = set()

    for item in container.get("onlineCourses") or []:
        if isinstance(item, str):
            code = item.strip().upper()
            if code in DEFAULT_ONLINE_COURSES:
                online_course_codes.add(code)
        elif isinstance(item, dict) and item.get("courseCode"):
            code = str(item["courseCode"]).strip().upper()
            if code in DEFAULT_ONLINE_COURSES:
                online_course_codes.add(code)

    online_course_codes.update(course["courseCode"] for course in arabic_courses)

    return {
        "semesterId": container.get("semesterId", payload.get("semesterId")),
        "days": container.get("days") or DEFAULT_DAYS,
        "regularTimeSlots": container.get("regularTimeSlots") or DEFAULT_REGULAR_SLOTS,
        "arabicOnlineTimeSlots": container.get("arabicOnlineTimeSlots") or DEFAULT_ONLINE_SLOTS,
        "onlineTimeSlots": container.get("onlineTimeSlots") or [],
        "aptechTimeSlots": container.get("aptechTimeSlots") or [],
        "targetGroupSize": safe_int(container.get("targetGroupSize"), 150),
        "sectionCapacity": safe_int(container.get("sectionCapacity"), 50),
        "onlineCourses": sorted(online_course_codes),
        "arabicCourses": arabic_courses,
        "aptechCourses": [
            normalize_course(
                raw,
                force_online=True,
                force_arabic_online=False,
                force_aptech=True,
            )
            for raw in container.get("aptechCourses", [])
            if isinstance(raw, dict)
        ],
        "courses": [],
        "regularCourses": courses,
        "instructors": [],
        "regularInstructors": regular_instructors,
        "arabicInstructors": arabic_instructors,
        "aptechInstructors": aptech_instructors,
        "studentGroups": container.get("studentGroups") if isinstance(container.get("studentGroups"), list) else [],
        "rooms": rooms,
        "scheduleUrl": container.get("scheduleUrl"),
        "outputScheduleUrl": container.get("outputScheduleUrl"),
    }


def load_json_from_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def load_json_from_url(url: str, timeout: int = 60) -> Dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def load_json_source(source: str) -> Dict[str, Any]:
    if is_url(source):
        return load_json_from_url(source)

    return load_json_from_file(Path(source))


def run_scheduler(input_data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_payload(input_data)
    engine = SchedulingEngine(normalized)
    return engine.generate_schedule()


def main() -> int:
    try:
        input_source = sys.argv[1] if len(sys.argv) > 1 else LOCAL_INPUT_FILE
        output_file = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_FILE

        if not is_url(input_source):
            input_path = Path(input_source)
            if not input_path.exists():
                raise FileNotFoundError(f"Input file not found: {input_path.resolve()}")

            print(f"Reading backend JSON from file: {input_path.resolve()}")
        else:
            print(f"Reading backend JSON from URL: {input_source}")

        raw_input = load_json_source(input_source)
        output = run_scheduler(raw_input)

        output_path = Path(output_file)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(output, file, ensure_ascii=False, indent=2)

        print(json.dumps(output, ensure_ascii=False, indent=2))
        print(f"Saved schedule to: {output_path.resolve()}")

        return 0

    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
