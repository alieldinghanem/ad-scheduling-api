from copy import deepcopy
from typing import Any, Dict, List


def _safe_list(value):
    return value if isinstance(value, list) else []


def _session_count(courses: List[Dict[str, Any]]) -> int:
    return sum(len(_safe_list(course.get("sessions"))) for course in courses)


def _course_code(course: Dict[str, Any]) -> str:
    return str(course.get("courseCode") or "").strip().upper()


def _is_english_aptech(course: Dict[str, Any]) -> bool:
    code = _course_code(course)
    name = str(course.get("courseName") or "").upper()
    return code.startswith("ENG") or "ENGLISH" in name


def _is_computer_aptech(course: Dict[str, Any]) -> bool:
    code = _course_code(course)
    name = str(course.get("courseName") or "").upper()
    return code.startswith("CS-") or "COMPUTER" in name


def _used_instructor_count(courses: List[Dict[str, Any]]) -> int:
    identities = set()
    for course in courses:
        for session in _safe_list(course.get("sessions")):
            identity = session.get("instructorId") or session.get("instructorName")
            if identity not in (None, ""):
                identities.add(str(identity))
    return len(identities)


def _annotate_arabic_courses(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    annotated = deepcopy(courses)
    for course in annotated:
        course["arabicMode"] = "ARABIC_ONLINE"
        course["schedulingRule"] = "ARABIC_INSTRUCTOR_ONLINE_SLOT"
        course["expectedTimeSlot"] = "17:00-19:00"
        course["generatedSessionCount"] = len(_safe_list(course.get("sessions")))

        for session in _safe_list(course.get("sessions")):
            session["arabicMode"] = "ARABIC_ONLINE"
            session["schedulingRule"] = "ARABIC_INSTRUCTOR_ONLINE_SLOT"
            session["expectedTimeSlot"] = "17:00-19:00"
            session["sourceInstructorId"] = session.get("instructorId")
            session["sourceInstructorName"] = session.get("instructorName")

    return annotated


def _annotate_aptech_courses(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    annotated = deepcopy(courses)
    for course in annotated:
        if not course.get("aptechMode"):
            if _is_english_aptech(course):
                course["aptechMode"] = "ENGLISH"
            elif _is_computer_aptech(course):
                course["aptechMode"] = "COMPUTER"
            else:
                course["aptechMode"] = "GENERIC"

        course.setdefault(
            "schedulingRule",
            "INSTRUCTOR_AVAILABILITY"
            if course.get("aptechMode") == "ENGLISH"
            else "TA_APTECH_DAY",
        )
        course["generatedSessionCount"] = len(_safe_list(course.get("sessions")))

        for index, session in enumerate(_safe_list(course.get("sessions")), start=1):
            session.setdefault("aptechMode", course.get("aptechMode"))
            session.setdefault("schedulingRule", course.get("schedulingRule"))
            session.setdefault("sourceInstructorId", session.get("instructorId"))
            session.setdefault("sourceInstructorName", session.get("instructorName"))
            session.setdefault("aptechGroupNumber", index)
            if course.get("aptechMode") == "COMPUTER":
                session.setdefault("aptechDay", session.get("dayOfWeek"))

    return annotated


def build_aptech_ara_output(
    arabic_courses: List[Dict[str, Any]],
    aptech_courses: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arabic = _annotate_arabic_courses(_safe_list(arabic_courses))
    aptech = _annotate_aptech_courses(_safe_list(aptech_courses))
    english_aptech = [course for course in aptech if course.get("aptechMode") == "ENGLISH"]
    computer_aptech = [course for course in aptech if course.get("aptechMode") == "COMPUTER"]

    return {
        "arabic": {
            "schedulingRule": "ARABIC_INSTRUCTOR_ONLINE_SLOT",
            "expectedTimeSlot": "17:00-19:00",
            "totalCourses": len(arabic),
            "totalSessions": _session_count(arabic),
            "courses": arabic,
        },
        "aptech": {
            "totalCourses": len(aptech),
            "totalSessions": _session_count(aptech),
            "english": {
                "schedulingRule": "INSTRUCTOR_AVAILABILITY",
                "totalCourses": len(english_aptech),
                "totalSessions": _session_count(english_aptech),
                "usedInstructorCount": _used_instructor_count(english_aptech),
                "courses": english_aptech,
            },
            "computer": {
                "schedulingRule": "TA_APTECH_DAY",
                "totalCourses": len(computer_aptech),
                "totalSessions": _session_count(computer_aptech),
                "usedInstructorCount": _used_instructor_count(computer_aptech),
                "courses": computer_aptech,
            },
            "courses": aptech,
        },
        "totalCourses": len(arabic) + len(aptech),
        "totalSessions": _session_count(arabic) + _session_count(aptech),
    }
