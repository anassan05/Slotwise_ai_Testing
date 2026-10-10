from __future__ import annotations

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


def past_date(days: int = 1) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def payload(**overrides):
    data = {
        "customer_name": "Avery Morgan",
        "service": "Consultation",
        "appointment_date": future_date(),
        "start_time": "09:00",
        "end_time": "09:30",
    }
    data.update(overrides)
    return data


def book(client, **overrides):
    return client.post("/api/appointments", json=payload(**overrides))


def test_successful_appointment_booking(client):
    response = book(client)

    assert response.status_code == 201
    body = response.get_json()
    assert body["appointment"]["status"] == "BOOKED"
    assert body["appointment"]["customer_name"] == "Avery Morgan"


def test_missing_required_fields(client):
    response = book(client, customer_name="")

    assert response.status_code == 400
    assert "Missing required" in response.get_json()["error"]


def test_invalid_date_and_time_formats(client):
    bad_date = book(client, appointment_date="31-12-2026")
    bad_time = book(client, start_time="9am")

    assert bad_date.status_code == 400
    assert bad_time.status_code == 400


def test_past_date_rejection(client):
    response = book(client, appointment_date=past_date())

    assert response.status_code == 400
    assert "past" in response.get_json()["error"]


def test_end_time_before_or_equal_start_time(client):
    equal = book(client, start_time="10:00", end_time="10:00")
    before = book(client, start_time="10:00", end_time="09:59")

    assert equal.status_code == 400
    assert before.status_code == 400


def test_overlapping_appointment_rejection(client):
    first = book(client, start_time="11:00", end_time="12:00")
    overlap = book(client, customer_name="Jordan Lee", start_time="11:30", end_time="12:30")

    assert first.status_code == 201
    assert overlap.status_code == 409


def test_non_overlapping_appointments_allowed(client):
    first = book(client, start_time="12:00", end_time="12:30")
    second = book(client, customer_name="Jordan Lee", start_time="12:30", end_time="13:00")

    assert first.status_code == 201
    assert second.status_code == 201


def test_booking_cancelled_slot_again(client):
    first = book(client, start_time="13:00", end_time="13:30")
    appointment_id = first.get_json()["appointment"]["id"]
    cancelled = client.post(f"/api/appointments/{appointment_id}/cancel")
    replacement = book(client, customer_name="Sam Rivera", start_time="13:00", end_time="13:30")

    assert cancelled.status_code == 200
    assert replacement.status_code == 201


def test_successful_cancellation(client):
    response = book(client, start_time="14:00", end_time="14:30")
    appointment_id = response.get_json()["appointment"]["id"]

    cancelled = client.post(f"/api/appointments/{appointment_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.get_json()["appointment"]["status"] == "CANCELLED"


def test_invalid_or_repeated_cancellation(client):
    missing = client.post("/api/appointments/999999/cancel")
    response = book(client, start_time="15:00", end_time="15:30")
    appointment_id = response.get_json()["appointment"]["id"]
    first = client.post(f"/api/appointments/{appointment_id}/cancel")
    second = client.post(f"/api/appointments/{appointment_id}/cancel")

    assert missing.status_code == 404
    assert first.status_code == 200
    assert second.status_code == 409


def test_data_persistence(tmp_path):
    db_path = str(tmp_path / "persistent.db")
    app = create_app({"TESTING": True, "DATABASE": db_path})
    first_client = app.test_client()
    response = first_client.post("/api/appointments", json=payload())
    appointment_id = response.get_json()["appointment"]["id"]

    second_app = create_app({"TESTING": True, "DATABASE": db_path})
    second_client = second_app.test_client()
    listed = second_client.get("/api/appointments")

    assert response.status_code == 201
    assert appointment_id in [item["id"] for item in listed.get_json()["appointments"]]


def test_invalid_requests_do_not_create_records(client):
    before = client.get("/api/appointments").get_json()["appointments"]
    response = book(client, start_time="16:00", end_time="15:00")
    after = client.get("/api/appointments").get_json()["appointments"]

    assert response.status_code == 400
    assert len(after) == len(before)


def test_database_uses_expected_columns(client):
    client.post("/api/appointments", json=payload(start_time="17:00", end_time="17:30"))
    app = client.application
    with get_connection(app.config["DATABASE"]) as conn:
        row = conn.execute("SELECT service, end_time FROM appointments LIMIT 1").fetchone()

    assert row["service"] == "Consultation"
    assert row["end_time"] == "17:30"


def test_database_summary_reports_sql_storage(client):
    client.post("/api/appointments", json=payload(start_time="18:00", end_time="18:30"))

    response = client.get("/api/database/summary")
    body = response.get_json()

    assert response.status_code == 200
    assert body["database"]["engine"] == "SQLite"
    assert body["database"]["file"] == "slotwise.db"
    assert body["database"]["tables"]["appointments"] == 1
