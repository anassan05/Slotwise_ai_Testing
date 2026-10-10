from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

from app import create_app
from database import get_connection


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "slotwise_test.db")})
    return app.test_client()


def future_date(days: int = 7) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def payload(**overrides):
    data = {
        "patient_name": "Avery Morgan",
        "mobile_number": "9876543210",
        "email": "avery@example.com",
        "service_id": "general_consultation",
        "appointment_date": future_date(),
        "start_time": "09:00",
    }
    data.update(overrides)
    return data


def book(client, **overrides):
    return client.post("/api/appointments", json=payload(**overrides))


def test_successful_booking_calculates_service_end_time(client):
    response = book(client, service_id="specialist_consultation", start_time="10:00", end_time="23:59")

    assert response.status_code == 201
    appointment = response.get_json()["appointment"]
    assert appointment["status"] == "BOOKED"
    assert appointment["patient_name"] == "Avery Morgan"
    assert appointment["mobile_number"] == "+919876543210"
    assert appointment["end_time"] == "10:30"


def test_browser_cannot_override_configured_duration(client):
    response = book(client, service_id="vaccination", start_time="11:00", end_time="16:00")

    assert response.status_code == 201
    assert response.get_json()["appointment"]["end_time"] == "11:15"


def test_unknown_service_is_rejected(client):
    response = book(client, service_id="secret_service")

    assert response.status_code == 400
    assert "valid appointment service" in response.get_json()["error"]


def test_required_patient_name_and_mobile_validation(client):
    missing_name = book(client, patient_name="")
    missing_mobile = book(client, mobile_number="")
    bad_mobile = book(client, mobile_number="12345")

    assert missing_name.status_code == 400
    assert missing_mobile.status_code == 400
    assert bad_mobile.status_code == 400


def test_optional_email_validation(client):
    without_email = book(client, email="")
    invalid_email = book(client, email="not-an-email")

    assert without_email.status_code == 201
    assert without_email.get_json()["appointment"]["email"] is None
    assert invalid_email.status_code == 400


def test_invalid_and_past_dates_are_rejected(client):
    bad_format = book(client, appointment_date="31-12-2026")
    past = book(client, appointment_date=(date.today() - timedelta(days=1)).isoformat())

    assert bad_format.status_code == 400
    assert past.status_code == 400
    assert "past" in past.get_json()["error"]


def test_clinic_hours_and_start_interval_are_enforced(client):
    outside = book(client, start_time="17:00")
    invalid_interval = book(client, start_time="09:07")

    assert outside.status_code == 400
    assert invalid_interval.status_code == 400


def test_overlapping_appointment_rejection(client):
    first = book(client, service_id="specialist_consultation", start_time="11:00")
    overlap = book(client, patient_name="Jordan Lee", service_id="general_consultation", start_time="11:15")

    assert first.status_code == 201
    assert overlap.status_code == 409


def test_back_to_back_appointments_are_allowed(client):
    first = book(client, service_id="specialist_consultation", start_time="12:00")
    second = book(client, patient_name="Jordan Lee", service_id="general_consultation", start_time="12:30")

    assert first.status_code == 201
    assert second.status_code == 201


def test_concurrent_conflicting_requests_allow_only_one_booking(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "concurrent.db")})

    def submit(patient_name):
        with app.test_client() as concurrent_client:
            return concurrent_client.post(
                "/api/appointments",
                json=payload(patient_name=patient_name, service_id="specialist_consultation", start_time="12:00"),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(submit, ["One Patient", "Two Patient"]))

    assert sorted(statuses) == [201, 409]


def test_booking_cancelled_slot_again(client):
    first = book(client, start_time="13:00")
    appointment_id = first.get_json()["appointment"]["id"]
    cancelled = client.post(f"/api/appointments/{appointment_id}/cancel")
    replacement = book(client, patient_name="Sam Rivera", start_time="13:00")

    assert cancelled.status_code == 200
    assert replacement.status_code == 201


def test_successful_and_repeated_cancellation(client):
    response = book(client, start_time="14:00")
    appointment_id = response.get_json()["appointment"]["id"]

    cancelled = client.post(f"/api/appointments/{appointment_id}/cancel")
    repeated = client.post(f"/api/appointments/{appointment_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.get_json()["appointment"]["status"] == "CANCELLED"
    assert repeated.status_code == 409


def test_data_persistence_and_legacy_migration(tmp_path):
    db_path = str(tmp_path / "persistent.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL,
                service TEXT NOT NULL, appointment_date TEXT NOT NULL,
                start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT, updated_at TEXT, cancelled_at TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO appointments (customer_name, service, appointment_date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("Legacy Patient", "Consultation", future_date(), "08:00", "08:15", "BOOKED"),
        )
        conn.commit()

    app = create_app({"TESTING": True, "DATABASE": db_path})
    client = app.test_client()
    listed = client.get("/api/appointments")

    assert listed.status_code == 200
    legacy = listed.get_json()["appointments"][0]
    assert legacy["patient_name"] == "Legacy Patient"
    assert legacy["mobile_number"] == ""


def test_invalid_requests_do_not_create_records(client):
    before = client.get("/api/appointments").get_json()["appointments"]
    response = book(client, start_time="16:35", service_id="specialist_consultation")
    after = client.get("/api/appointments").get_json()["appointments"]

    assert response.status_code == 400
    assert len(after) == len(before)


def test_availability_returns_duration_aware_slots(client):
    response = client.get(f"/api/availability?date={future_date()}&service_id=specialist_consultation")

    assert response.status_code == 200
    slots = response.get_json()["slots"]
    assert slots[0]["start_time"] == "09:00"
    assert slots[0]["end_time"] == "09:30"


def test_services_are_backend_configured(client):
    response = client.get("/api/services")

    assert response.status_code == 200
    assert {service["id"] for service in response.get_json()["services"]} >= {
        "general_consultation",
        "specialist_consultation",
        "vaccination",
    }


def test_database_summary_reports_sql_storage(client):
    book(client, start_time="15:00")

    response = client.get("/api/database/summary")
    body = response.get_json()

    assert response.status_code == 200
    assert body["database"]["engine"] == "SQLite"
    assert body["database"]["file"] == "slotwise.db"
    assert body["database"]["tables"]["appointments"] == 1
