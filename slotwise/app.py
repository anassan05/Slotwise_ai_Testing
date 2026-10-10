from __future__ import annotations

from datetime import date, datetime, time, timedelta
import os
import re
from unicodedata import category

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from clinic_config import CLINIC_CLOSE, CLINIC_OPEN, SERVICE_BY_ID, SERVICE_BY_NAME, SERVICES, SLOT_INTERVAL_MINUTES
from database import ACTIVE_STATUSES, get_connection, init_db, row_to_dict, transaction


DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


class ValidationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-secret"),
        DATABASE=os.environ.get("SLOTWISE_DB"),
        JSON_SORT_KEYS=False,
        DISABLE_OVERLAP_VALIDATION_FOR_DEMO=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    )
    if config:
        app.config.update(config)

    init_db(app.config.get("DATABASE"))

    @app.errorhandler(ValidationError)
    def handle_validation(error: ValidationError):
        return jsonify({"ok": False, "error": error.message}), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"ok": False, "error": "Resource not found."}), 404

    @app.errorhandler(Exception)
    def handle_exception(error):
        app.logger.exception("Unhandled server error: %s", error)
        return jsonify({"ok": False, "error": "Unexpected server error."}), 500

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/login")
    def login_page():
        return render_template("login.html")

    @app.get("/register")
    def register_page():
        return render_template("register.html")

    @app.get("/api/auth/me")
    def auth_me():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"ok": True, "authenticated": False, "user": None})
        with get_connection(app.config.get("DATABASE")) as conn:
            user = conn.execute(
                "SELECT id, full_name, email, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not user:
            session.clear()
            return jsonify({"ok": True, "authenticated": False, "user": None})
        return jsonify({"ok": True, "authenticated": True, "user": row_to_dict(user)})

    @app.post("/api/auth/register")
    def register():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")
        full_name, email, password = validate_auth_payload(payload)
        with transaction(app.config.get("DATABASE"), immediate=True) as conn:
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise ValidationError("An account with that email already exists.", 409)
            cursor = conn.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (full_name, email, generate_password_hash(password)),
            )
            user_id = cursor.lastrowid
        session["user_id"] = user_id
        return jsonify({"ok": True, "message": "Account created.", "user": {"full_name": full_name, "email": email}}), 201

    @app.post("/api/auth/login")
    def login():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if not email or not password:
            raise ValidationError("Email and password are required.")
        with get_connection(app.config.get("DATABASE")) as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            raise ValidationError("Email or password is incorrect.", 401)
        session["user_id"] = user["id"]
        return jsonify({"ok": True, "authenticated": True, "message": "Signed in.", "user": {"full_name": user["full_name"], "email": user["email"]}})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True, "message": "Signed out."})

    @app.get("/api/appointments")
    def list_appointments():
        with get_connection(app.config.get("DATABASE")) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM appointments
                ORDER BY appointment_date DESC, start_time DESC, id DESC
                """
            ).fetchall()
        return jsonify({"ok": True, "appointments": [row_to_dict(row) for row in rows]})

    @app.get("/api/services")
    def list_services():
        return jsonify(
            {
                "ok": True,
                "services": [
                    {"id": service.id, "name": service.name, "duration_minutes": service.duration_minutes}
                    for service in SERVICES
                ],
            }
        )

    @app.get("/api/availability")
    def availability():
        appointment_date = request.args.get("date", "")
        service_id = request.args.get("service_id", "")
        service = SERVICE_BY_ID.get(service_id)
        if not service:
            raise ValidationError("Select a valid appointment service.")
        parsed_date = _parse_date(appointment_date)
        _validate_appointment_date(parsed_date)
        with get_connection(app.config.get("DATABASE")) as conn:
            booked = conn.execute(
                """
                SELECT start_time, end_time
                FROM appointments
                WHERE appointment_date = ? AND status IN (?)
                """,
                (parsed_date.isoformat(), ACTIVE_STATUSES[0]),
            ).fetchall()
        slots = []
        for start in _slot_starts(parsed_date, service.duration_minutes):
            end = datetime.combine(parsed_date, start) + timedelta(minutes=service.duration_minutes)
            slots.append(
                {
                    "start_time": start.strftime(TIME_FORMAT),
                    "end_time": end.strftime(TIME_FORMAT),
                    "available": not any(
                        start.strftime(TIME_FORMAT) < row["end_time"]
                        and end.strftime(TIME_FORMAT) > row["start_time"]
                        for row in booked
                    ),
                }
            )
        return jsonify({"ok": True, "date": parsed_date.isoformat(), "service": service.id, "slots": slots})

    @app.post("/api/appointments")
    def create_appointment():
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValidationError("Request body must be a JSON object.")
        appointment = validate_appointment_payload(payload)

        with transaction(app.config.get("DATABASE"), immediate=True) as conn:
            if _overlap_exists(conn, appointment) and not _demo_overlap_disabled(app):
                raise ValidationError("This slot overlaps an active appointment.", 409)

            cursor = conn.execute(
                """
                INSERT INTO appointments
                    (customer_name, patient_name, mobile_number, email, service, service_id,
                     appointment_date, start_time, end_time, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'BOOKED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    appointment["patient_name"],
                    appointment["patient_name"],
                    appointment["mobile_number"],
                    appointment["email"],
                    appointment["service"],
                    appointment["service_id"],
                    appointment["appointment_date"],
                    appointment["start_time"],
                    appointment["end_time"],
                ),
            )
            created = conn.execute("SELECT * FROM appointments WHERE id = ?", (cursor.lastrowid,)).fetchone()

        return jsonify({"ok": True, "message": "Appointment booked.", "appointment": row_to_dict(created)}), 201

    @app.post("/api/appointments/<int:appointment_id>/cancel")
    def cancel_appointment(appointment_id: int):
        with transaction(app.config.get("DATABASE"), immediate=True) as conn:
            row = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
            if not row:
                raise ValidationError("Appointment not found.", 404)
            if row["status"] == "CANCELLED":
                raise ValidationError("Appointment is already cancelled.", 409)

            conn.execute(
                """
                UPDATE appointments
                SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (appointment_id,),
            )
            updated = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()

        return jsonify({"ok": True, "message": "Appointment cancelled.", "appointment": row_to_dict(updated)})

    @app.get("/api/stats")
    def stats():
        with get_connection(app.config.get("DATABASE")) as conn:
            total = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
            cancelled = conn.execute("SELECT COUNT(*) FROM appointments WHERE status = 'CANCELLED'").fetchone()[0]
            upcoming = conn.execute(
                """
                SELECT COUNT(*)
                FROM appointments
                WHERE status = 'BOOKED' AND appointment_date >= ?
                """,
                (date.today().isoformat(),),
            ).fetchone()[0]
        return jsonify({"ok": True, "stats": {"total": total, "upcoming": upcoming, "cancelled": cancelled}})

    @app.get("/api/database/summary")
    def database_summary():
        with get_connection(app.config.get("DATABASE")) as conn:
            appointments = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
            test_runs = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
            test_results = conn.execute("SELECT COUNT(*) FROM test_results").fetchone()[0]
            latest_run = conn.execute(
                """
                SELECT id, mode, started_at, total, passed, failed, pass_percentage
                FROM test_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return jsonify(
            {
                "ok": True,
                "database": {
                    "engine": "SQLite",
                    "file": "slotwise.db",
                    "tables": {
                        "appointments": appointments,
                        "test_runs": test_runs,
                        "test_results": test_results,
                    },
                    "latest_run": row_to_dict(latest_run) if latest_run else None,
                },
            }
        )

    @app.post("/api/testpilot/run")
    def run_testpilot():
        from testpilot.result_store import ResultStore
        from testpilot.runner import run_scenarios

        result = run_scenarios()
        ResultStore(app.config.get("DATABASE")).store_run(result)
        return jsonify({"ok": True, "run": result})

    @app.post("/api/testpilot/defect-demo")
    def run_defect_demo():
        from testpilot.result_store import ResultStore
        from testpilot.runner import run_defect_demonstration

        result = run_defect_demonstration()
        ResultStore(app.config.get("DATABASE")).store_run(result["defective"])
        ResultStore(app.config.get("DATABASE")).store_run(result["restored"])
        return jsonify({"ok": True, "demo": result})

    @app.get("/api/testpilot/history")
    def testpilot_history():
        from testpilot.result_store import ResultStore

        return jsonify({"ok": True, "history": ResultStore(app.config.get("DATABASE")).history()})

    return app


def _demo_overlap_disabled(app: Flask) -> bool:
    return bool(app.testing and app.config.get("DISABLE_OVERLAP_VALIDATION_FOR_DEMO"))


def validate_appointment_payload(payload: dict) -> dict:
    patient_name_value = payload.get("patient_name") or payload.get("customer_name")
    service_id = str(payload.get("service_id", "")).strip()
    if not service_id and str(payload.get("service", "")).strip().casefold() == "consultation":
        service_id = "general_consultation"
    required = {
        "patient_name": patient_name_value,
        "mobile_number": payload.get("mobile_number"),
        "service_id": service_id,
        "appointment_date": payload.get("appointment_date"),
        "start_time": payload.get("start_time"),
    }
    missing = [field for field, value in required.items() if not str(value or "").strip()]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}.")

    appointment_date = _parse_date(str(payload["appointment_date"]))
    _validate_appointment_date(appointment_date)
    service = SERVICE_BY_ID.get(service_id)
    if not service:
        raise ValidationError("Select a valid appointment service.")

    try:
        start_time = datetime.strptime(str(payload["start_time"]), TIME_FORMAT).time()
    except ValueError as exc:
        raise ValidationError("Start time must use HH:MM 24-hour format.") from exc
    if start_time.strftime(TIME_FORMAT) != str(payload["start_time"]):
        raise ValidationError("Times must use HH:MM 24-hour format.")
    if start_time.minute % SLOT_INTERVAL_MINUTES:
        raise ValidationError(f"Start time must be in {SLOT_INTERVAL_MINUTES}-minute increments.")
    end_datetime = datetime.combine(appointment_date, start_time) + timedelta(minutes=service.duration_minutes)
    end_time = end_datetime.time()
    if start_time < CLINIC_OPEN or end_time > CLINIC_CLOSE:
        raise ValidationError("This appointment falls outside clinic hours (9:00 AM to 5:00 PM).")
    if appointment_date == date.today() and start_time <= datetime.now().time().replace(second=0, microsecond=0):
        raise ValidationError("Select a future appointment time.")

    patient_name = _validate_text_field("Patient name", patient_name_value, min_length=2, max_length=80)
    mobile_number = _normalize_mobile(payload["mobile_number"])
    email = _normalize_email(payload.get("email"))

    return {
        "patient_name": patient_name,
        "mobile_number": mobile_number,
        "email": email,
        "service": service.name,
        "service_id": service.id,
        "appointment_date": appointment_date.isoformat(),
        "start_time": start_time.strftime(TIME_FORMAT),
        "end_time": end_time.strftime(TIME_FORMAT),
    }


def _parse_date(value: str) -> date:
    try:
        parsed = datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise ValidationError("Date must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise ValidationError("Date must use YYYY-MM-DD format.")
    return parsed


def _validate_appointment_date(appointment_date: date) -> None:
    if appointment_date < date.today():
        raise ValidationError("Cannot book appointments in the past.")


def _normalize_mobile(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValidationError("Enter a valid 10-digit Indian mobile number.")
    return f"+91{digits}"


def _normalize_email(value: object) -> str | None:
    email = str(value or "").strip().lower()
    if not email:
        return None
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValidationError("Enter a valid email address.")
    return email


def _slot_starts(appointment_date: date, duration_minutes: int) -> list[time]:
    start = datetime.combine(appointment_date, CLINIC_OPEN)
    close = datetime.combine(appointment_date, CLINIC_CLOSE)
    current = start
    starts = []
    while current + timedelta(minutes=duration_minutes) <= close:
        if appointment_date != date.today() or current.time() > datetime.now().time().replace(second=0, microsecond=0):
            starts.append(current.time())
        current += timedelta(minutes=SLOT_INTERVAL_MINUTES)
    return starts


def validate_auth_payload(payload: dict) -> tuple[str, str, str]:
    full_name = _validate_text_field("Full name", payload.get("full_name", ""), min_length=2, max_length=80)
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValidationError("Enter a valid email address.")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if len(password) > 128:
        raise ValidationError("Password must be 128 characters or fewer.")
    return full_name, email, password


def _validate_text_field(label: str, value: object, min_length: int, max_length: int) -> str:
    text = str(value).strip()
    if len(text) < min_length:
        raise ValidationError(f"{label} must be at least {min_length} characters.")
    if len(text) > max_length:
        raise ValidationError(f"{label} must be {max_length} characters or fewer.")
    if any(category(character).startswith("C") for character in text):
        raise ValidationError(f"{label} cannot contain control characters.")
    return text


def _overlap_exists(conn, appointment: dict) -> bool:
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    row = conn.execute(
        f"""
        SELECT 1
        FROM appointments
        WHERE appointment_date = ?
          AND status IN ({placeholders})
          AND start_time < ?
          AND end_time > ?
        LIMIT 1
        """,
        (
            appointment["appointment_date"],
            *ACTIVE_STATUSES,
            appointment["end_time"],
            appointment["start_time"],
        ),
    ).fetchone()
    return row is not None


def main() -> None:
    app = create_app()
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )


if __name__ == "__main__":
    main()
