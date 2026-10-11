from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re
import sqlite3

from clinic_config import CLINIC_CLOSE, CLINIC_OPEN, DOCTOR_BY_ID, DOCTORS, SERVICE_BY_ID, SERVICES, SLOT_INTERVAL_MINUTES
from database import ACTIVE_STATUSES, get_connection, is_lock_error, row_to_dict, transaction

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


class BookingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_services() -> list[dict]:
    return [{"id": item.id, "name": item.name, "duration_minutes": item.duration_minutes} for item in SERVICES]


def list_doctors() -> list[dict]:
    return [{"id": item.id, "name": item.name, "specialty": item.specialty} for item in DOCTORS]


def prepare_booking(payload: dict) -> dict:
    patient_name_value = payload.get("patient_name") or payload.get("customer_name")
    service_id = str(payload.get("service_id", "")).strip()
    if not service_id and str(payload.get("service", "")).strip().casefold() == "consultation":
        service_id = "general_consultation"
    required = {
        "patient_name": patient_name_value,
        "mobile_number": payload.get("mobile_number"),
        "doctor_id": payload.get("doctor_id"),
        "service_id": service_id,
        "appointment_date": payload.get("appointment_date"),
        "start_time": payload.get("start_time"),
    }
    missing = [field for field, value in required.items() if not str(value or "").strip()]
    if missing:
        raise BookingError(f"Missing required field(s): {', '.join(missing)}.")

    appointment_date = parse_date(str(payload["appointment_date"]))
    if appointment_date < date.today():
        raise BookingError("Cannot book appointments in the past.")
    service = SERVICE_BY_ID.get(service_id)
    if not service:
        raise BookingError("Select a valid appointment service.")
    doctor_id = str(payload.get("doctor_id", "")).strip()
    doctor = DOCTOR_BY_ID.get(doctor_id)
    if not doctor:
        raise BookingError("Select a valid doctor.")

    try:
        start_time = datetime.strptime(str(payload["start_time"]), TIME_FORMAT).time()
    except ValueError as exc:
        raise BookingError("Start time must use HH:MM 24-hour format.") from exc
    if start_time.strftime(TIME_FORMAT) != str(payload["start_time"]):
        raise BookingError("Times must use HH:MM 24-hour format.")
    if start_time.minute % SLOT_INTERVAL_MINUTES:
        raise BookingError(f"Start time must be in {SLOT_INTERVAL_MINUTES}-minute increments.")

    end_datetime = datetime.combine(appointment_date, start_time) + timedelta(minutes=service.duration_minutes)
    end_time = end_datetime.time()
    if start_time < CLINIC_OPEN or end_time > CLINIC_CLOSE:
        raise BookingError("This appointment falls outside clinic hours (9:00 AM to 5:00 PM).")
    if appointment_date == date.today() and start_time <= datetime.now().time().replace(second=0, microsecond=0):
        raise BookingError("Select a future appointment time.")

    return {
        "patient_name": normalize_name(patient_name_value),
        "mobile_number": normalize_mobile(payload["mobile_number"]),
        "email": normalize_email(payload.get("email")),
        "doctor_id": doctor.id,
        "doctor_name": doctor.name,
        "service": service.name,
        "service_id": service.id,
        "appointment_date": appointment_date.isoformat(),
        "start_time": start_time.strftime(TIME_FORMAT),
        "end_time": end_time.strftime(TIME_FORMAT),
    }


def create_booking(db_path: str | None, payload: dict, disable_overlap: bool = False) -> dict:
    appointment = prepare_booking(payload)
    try:
        with transaction(db_path, immediate=True) as conn:
            if _overlap_exists(conn, appointment) and not disable_overlap:
                raise BookingError("This slot overlaps an active appointment.", 409)
            cursor = conn.execute(
                """
                INSERT INTO appointments
                    (customer_name, patient_name, mobile_number, email, doctor_id, doctor_name, service, service_id,
                     appointment_date, start_time, end_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BOOKED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    appointment["patient_name"], appointment["patient_name"], appointment["mobile_number"],
                    appointment["email"], appointment["doctor_id"], appointment["doctor_name"],
                    appointment["service"], appointment["service_id"],
                    appointment["appointment_date"], appointment["start_time"], appointment["end_time"],
                ),
            )
            row = conn.execute("SELECT * FROM appointments WHERE id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.OperationalError as exc:
        raise _booking_error_from_sqlite(exc) from exc
    return row_to_dict(row)


def cancel_booking(db_path: str | None, appointment_id: int) -> dict:
    try:
        with transaction(db_path, immediate=True) as conn:
            row = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
            if not row:
                raise BookingError("Appointment not found.", 404)
            if row["status"] == "CANCELLED":
                raise BookingError("Appointment is already cancelled.", 409)
            conn.execute(
                """
                UPDATE appointments
                SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (appointment_id,),
            )
            updated = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
    except sqlite3.OperationalError as exc:
        raise _booking_error_from_sqlite(exc) from exc
    return row_to_dict(updated)


def available_slots(db_path: str | None, appointment_date: str, service_id: str, doctor_id: str) -> list[dict]:
    service = SERVICE_BY_ID.get(service_id)
    if not service:
        raise BookingError("Select a valid appointment service.")
    if doctor_id not in DOCTOR_BY_ID:
        raise BookingError("Select a valid doctor.")
    parsed_date = parse_date(appointment_date)
    if parsed_date < date.today():
        raise BookingError("Cannot book appointments in the past.")
    with get_connection(db_path) as conn:
        booked = _active_bookings_for_doctor(conn, parsed_date.isoformat(), doctor_id)
    slots = []
    for start in slot_starts(parsed_date, service.duration_minutes):
        end = datetime.combine(parsed_date, start) + timedelta(minutes=service.duration_minutes)
        start_text, end_text = start.strftime(TIME_FORMAT), end.strftime(TIME_FORMAT)
        slots.append({"start_time": start_text, "end_time": end_text, "available": not any(start_text < row["end_time"] and end_text > row["start_time"] for row in booked)})
    return slots


def parse_date(value: str) -> date:
    try:
        parsed = datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise BookingError("Date must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise BookingError("Date must use YYYY-MM-DD format.")
    return parsed


def slot_starts(appointment_date: date, duration_minutes: int) -> list[time]:
    current = datetime.combine(appointment_date, CLINIC_OPEN)
    close = datetime.combine(appointment_date, CLINIC_CLOSE)
    starts = []
    while current + timedelta(minutes=duration_minutes) <= close:
        if appointment_date != date.today() or current.time() > datetime.now().time().replace(second=0, microsecond=0):
            starts.append(current.time())
        current += timedelta(minutes=SLOT_INTERVAL_MINUTES)
    return starts


def normalize_name(value: object) -> str:
    name = " ".join(str(value or "").split())
    if len(name) < 2 or len(name) > 80 or any(ord(character) < 32 for character in name):
        raise BookingError("Patient name must be between 2 and 80 characters.")
    return name


def normalize_mobile(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise BookingError("Enter a valid 10-digit Indian mobile number.")
    return f"+91{digits}"


def normalize_email(value: object) -> str | None:
    email = str(value or "").strip().lower()
    if not email:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise BookingError("Enter a valid email address.")
    return email


def _overlap_exists(conn, appointment: dict) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM appointments
        WHERE appointment_date = ? AND doctor_id = ? AND status IN (?)
          AND start_time < ? AND end_time > ?
        LIMIT 1
        """,
        _overlap_params(appointment),
    ).fetchone()
    return row is not None


def _active_bookings_for_doctor(conn, appointment_date: str, doctor_id: str):
    return conn.execute(
        """
        SELECT start_time, end_time
        FROM appointments
        WHERE appointment_date = ? AND doctor_id = ? AND status IN (?)
        """,
        (appointment_date, doctor_id, ACTIVE_STATUSES[0]),
    ).fetchall()


def _overlap_params(appointment: dict) -> tuple:
    return (
        appointment["appointment_date"],
        appointment["doctor_id"],
        ACTIVE_STATUSES[0],
        appointment["end_time"],
        appointment["start_time"],
    )


def _booking_error_from_sqlite(error: sqlite3.OperationalError) -> BookingError:
    if is_lock_error(error):
        return BookingError("The booking database is busy. Please retry in a moment.", 503)
    return BookingError("The booking database could not complete the request.", 500)
