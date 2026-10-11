from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    business_rule: str
    steps: list[dict]
    expected_status: int
    expected_result: str
    expected_response_conditions: list[dict] = field(default_factory=list)
    expected_database_changes: list[dict] = field(default_factory=list)


def future_date(days: int = 7) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def past_date(days: int = 1) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def valid_payload(**overrides) -> dict:
    payload = {
        "patient_name": "Avery Morgan",
        "mobile_number": "9876543210",
        "email": "avery@example.com",
        "doctor_id": "dr_rao",
        "service_id": "general_consultation",
        "appointment_date": future_date(),
        "start_time": "10:00",
    }
    payload.update(overrides)
    return payload


def auth_payload(**overrides) -> dict:
    payload = {
        "full_name": "TestPilot User",
        "email": "testpilot@example.com",
        "password": "secure-pass-123",
    }
    payload.update(overrides)
    return payload


def generate_scenarios() -> list[Scenario]:
    return [
        Scenario(
            "auth_register_success",
            "User registration",
            "A valid name, email, and password create a new account securely.",
            [{"method": "POST", "path": "/api/auth/register", "json": auth_payload()}],
            201,
            "registered",
        ),
        Scenario(
            "auth_login_success",
            "User login",
            "A registered user can authenticate with the correct password.",
            [
                {"method": "POST", "path": "/api/auth/register", "json": auth_payload()},
                {"method": "POST", "path": "/api/auth/login", "json": {"email": "testpilot@example.com", "password": "secure-pass-123"}},
            ],
            200,
            "authenticated",
        ),
        Scenario(
            "auth_invalid_login",
            "Invalid login rejected",
            "Incorrect credentials are rejected without authenticating the user.",
            [
                {"method": "POST", "path": "/api/auth/register", "json": auth_payload()},
                {"method": "POST", "path": "/api/auth/login", "json": {"email": "testpilot@example.com", "password": "wrong-password"}, "expect_error_contains": "incorrect"},
            ],
            401,
            "authentication_error",
        ),
        Scenario(
            "service_duration_calculated",
            "Service duration is server-controlled",
            "The selected service determines the end time; browser-supplied end times are ignored.",
            [{"method": "POST", "path": "/api/appointments", "json": valid_payload(service_id="specialist_consultation", start_time="09:00", end_time="23:59")}],
            201,
            "created",
            expected_response_conditions=[
                {"path": "appointment.end_time", "equals": "09:30"},
                {"path": "appointment.service_id", "equals": "specialist_consultation"},
            ],
            expected_database_changes=[{"table": "appointments", "delta": 1}],
        ),
        Scenario(
            "unknown_service_rejected",
            "Unknown service rejected",
            "Only services from the backend clinic configuration can be booked.",
            [{"method": "POST", "path": "/api/appointments", "json": valid_payload(service_id="unknown_service"), "expect_error_contains": "valid appointment service"}],
            400,
            "validation_error",
            expected_response_conditions=[{"path": "error", "contains": "valid appointment service"}],
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
        Scenario(
            "mobile_required",
            "Patient mobile number required",
            "A patient booking must include a valid Indian mobile number.",
            [{"method": "POST", "path": "/api/appointments", "json": valid_payload(mobile_number=""), "expect_error_contains": "mobile_number"}],
            400,
            "validation_error",
            expected_response_conditions=[{"path": "error", "contains": "mobile_number"}],
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
        Scenario(
            "booking_success",
            "Successful appointment booking",
            "A complete future appointment with a valid time range is accepted.",
            [{"method": "POST", "path": "/api/appointments", "json": valid_payload()}],
            201,
            "created",
            expected_response_conditions=[{"path": "appointment.status", "equals": "BOOKED"}],
            expected_database_changes=[{"table": "appointments", "delta": 1}],
        ),
        Scenario(
            "missing_required_fields",
            "Missing required fields",
            "Customer name, service, date, start time and end time are required.",
            [
                {
                    "method": "POST",
                    "path": "/api/appointments",
                    "json": valid_payload(patient_name=""),
                    "expect_error_contains": "Missing required",
                }
            ],
            400,
            "validation_error",
            expected_response_conditions=[{"path": "error", "contains": "Missing required"}],
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
        Scenario(
            "invalid_formats",
            "Invalid date and time formats",
            "Dates must be YYYY-MM-DD and times must be HH:MM.",
            [
                {
                    "method": "POST",
                    "path": "/api/appointments",
                    "json": valid_payload(appointment_date="10/31/2026"),
                    "expect_error_contains": "YYYY-MM-DD",
                }
            ],
            400,
            "validation_error",
            expected_response_conditions=[{"path": "error", "contains": "YYYY-MM-DD"}],
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
        Scenario(
            "past_date_rejected",
            "Past-date rejection",
            "Appointments cannot be booked in the past.",
            [
                {
                    "method": "POST",
                    "path": "/api/appointments",
                    "json": valid_payload(appointment_date=past_date()),
                    "expect_error_contains": "past",
                }
            ],
            400,
            "validation_error",
            expected_response_conditions=[{"path": "error", "contains": "past"}],
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
        Scenario(
            "invalid_time_range",
            "End time before or equal to start time",
            "An appointment end time must be after its start time.",
            [
                {
                    "method": "POST",
                    "path": "/api/appointments",
                    "json": valid_payload(start_time="11:07"),
                    "expect_error_contains": "increments",
                }
            ],
            400,
            "validation_error",
            expected_response_conditions=[{"path": "error", "contains": "increments"}],
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
        Scenario(
            "overlap_rejected",
            "Overlapping appointment rejection",
            "Active appointment times cannot overlap on the same date.",
            [
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(service_id="specialist_consultation", start_time="13:00")},
                {
                    "method": "POST",
                    "path": "/api/appointments",
                    "json": valid_payload(patient_name="Jordan Lee", start_time="13:15"),
                    "expect_error_contains": "overlaps",
                },
            ],
            409,
            "conflict",
            expected_response_conditions=[{"path": "error", "contains": "overlaps"}],
            expected_database_changes=[{"table": "appointments", "delta": 1}],
        ),
        Scenario(
            "non_overlap_allowed",
            "Non-overlapping appointments allowed",
            "Adjacent or separate appointments on the same day are allowed.",
            [
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(service_id="specialist_consultation", start_time="15:00")},
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(patient_name="Riley Chen", start_time="15:30")},
            ],
            201,
            "created",
            expected_response_conditions=[{"path": "appointment.status", "equals": "BOOKED"}],
            expected_database_changes=[{"table": "appointments", "delta": 2}],
        ),
        Scenario(
            "cancelled_slot_rebooked",
            "Booking a cancelled slot again",
            "Cancelled appointments release their time slot for a later booking.",
            [
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(service_id="specialist_consultation", start_time="16:00"), "save_as": "booking"},
                {"method": "POST", "path": "/api/appointments/{booking.id}/cancel"},
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(patient_name="Sam Rivera", start_time="16:00")},
            ],
            201,
            "created",
            expected_response_conditions=[{"path": "appointment.status", "equals": "BOOKED"}],
            expected_database_changes=[{"table": "appointments", "delta": 2}],
        ),
        Scenario(
            "cancel_success",
            "Successful cancellation",
            "A booked appointment can be cancelled once.",
            [
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(start_time="16:30"), "save_as": "booking"},
                {"method": "POST", "path": "/api/appointments/{booking.id}/cancel"},
            ],
            200,
            "cancelled",
            expected_response_conditions=[{"path": "appointment.status", "equals": "CANCELLED"}],
            expected_database_changes=[{"table": "appointments", "delta": 1}],
        ),
        Scenario(
            "repeat_cancel_rejected",
            "Invalid or repeated cancellation",
            "A cancelled appointment cannot be cancelled again.",
            [
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(start_time="16:00"), "save_as": "booking"},
                {"method": "POST", "path": "/api/appointments/{booking.id}/cancel"},
                {"method": "POST", "path": "/api/appointments/{booking.id}/cancel"},
            ],
            409,
            "conflict",
            expected_response_conditions=[{"path": "error", "contains": "already cancelled"}],
            expected_database_changes=[{"table": "appointments", "delta": 1}],
        ),
        Scenario(
            "data_persistence",
            "Data persistence",
            "Created appointments are returned by the list endpoint from SQLite.",
            [
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(start_time="15:00"), "save_as": "booking"},
                {"method": "GET", "path": "/api/appointments", "assert_contains_saved": "booking"},
            ],
            200,
            "listed",
            expected_database_changes=[{"table": "appointments", "delta": 1}],
        ),
        Scenario(
            "invalid_requests_no_records",
            "Invalid requests do not create records",
            "Validation failures must not insert appointment rows.",
            [
                {"method": "GET", "path": "/api/appointments", "save_count_as": "before", "save_db_count_as": "before_db"},
                {"method": "POST", "path": "/api/appointments", "json": valid_payload(start_time="16:07")},
                {
                    "method": "GET",
                    "path": "/api/appointments",
                    "assert_count_unchanged": "before",
                    "assert_db_count_unchanged": "before_db",
                    "assert_result": "no_insert",
                },
            ],
            200,
            "no_insert",
            expected_database_changes=[{"table": "appointments", "delta": 0}],
        ),
    ]


def generate_defect_overlap_scenario() -> Scenario:
    scenario = deepcopy([s for s in generate_scenarios() if s.id == "overlap_rejected"][0])
    return Scenario(
        "defect_overlap_rejected",
        scenario.name,
        scenario.business_rule,
        scenario.steps,
        scenario.expected_status,
        scenario.expected_result,
        scenario.expected_response_conditions,
        scenario.expected_database_changes,
    )
