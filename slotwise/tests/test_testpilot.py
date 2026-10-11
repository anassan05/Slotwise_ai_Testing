from __future__ import annotations

from datetime import date, timedelta

from app import create_app
from database import get_connection
from testpilot.result_store import ResultStore
from testpilot.runner import run_defect_demonstration, run_scenarios
from testpilot.scenario_generator import generate_scenarios


def booking_payload(**overrides):
    payload = {
        "patient_name": "Production Patient",
        "mobile_number": "9876543210",
        "email": "",
        "doctor_id": "dr_rao",
        "service_id": "general_consultation",
        "appointment_date": (date.today() + timedelta(days=20)).isoformat(),
        "start_time": "09:00",
    }
    payload.update(overrides)
    return payload


def test_scenario_generator_covers_required_business_rules():
    scenarios = generate_scenarios()

    assert len(scenarios) >= 12
    assert {scenario.id for scenario in scenarios} >= {
        "booking_success",
        "missing_required_fields",
        "invalid_formats",
        "past_date_rejected",
        "invalid_time_range",
        "overlap_rejected",
        "non_overlap_allowed",
        "cancelled_slot_rebooked",
        "cancel_success",
        "repeat_cancel_rejected",
        "data_persistence",
        "invalid_requests_no_records",
    }
    duration = next(scenario for scenario in scenarios if scenario.id == "service_duration_calculated")
    invalid = next(scenario for scenario in scenarios if scenario.id == "invalid_requests_no_records")
    assert duration.expected_response_conditions
    assert duration.expected_database_changes == [{"table": "appointments", "delta": 1}]
    assert invalid.expected_database_changes == [{"table": "appointments", "delta": 0}]


def test_testpilot_runs_real_scenarios():
    run = run_scenarios()

    assert run["total"] >= 12
    assert run["passed"] == run["total"]
    assert all(result["actual_status"] is not None for result in run["results"])
    assert all("database changes" in result["checks"] or result["scenario_id"].startswith("auth_") or result["scenario_id"] in {"mobile_required", "invalid_formats", "past_date_rejected", "invalid_time_range"} for result in run["results"])


def test_result_store_persists_summary_and_results(tmp_path):
    db_path = str(tmp_path / "results.db")
    run = run_scenarios()

    run_id = ResultStore(db_path).store_run(run)
    history = ResultStore(db_path).history()

    assert run_id == 1
    assert history[0]["passed"] == run["passed"]
    assert len(history[0]["results"]) == run["total"]


def test_defect_demonstration_fails_then_passes():
    demo = run_defect_demonstration()

    assert demo["defective"]["failed"] == 1
    assert demo["defective"]["results"][0]["passed"] is False
    assert demo["restored"]["passed"] == 1
    assert demo["restored"]["results"][0]["passed"] is True


def test_testpilot_ignores_production_database_config_for_scenarios(tmp_path):
    production_db = str(tmp_path / "production.db")
    app = create_app({"TESTING": True, "DATABASE": production_db})
    client = app.test_client()
    created = client.post("/api/appointments", json=booking_payload())
    assert created.status_code == 201

    with get_connection(production_db) as conn:
        before = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]

    run = run_scenarios(app_config={"DATABASE": production_db})

    with get_connection(production_db) as conn:
        after = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]

    assert run["passed"] == run["total"]
    assert after == before
