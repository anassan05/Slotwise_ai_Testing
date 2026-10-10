from __future__ import annotations

from testpilot.result_store import ResultStore
from testpilot.runner import run_defect_demonstration, run_scenarios
from testpilot.scenario_generator import generate_scenarios


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


def test_testpilot_runs_real_scenarios():
    run = run_scenarios()

    assert run["total"] >= 12
    assert run["passed"] == run["total"]
    assert all(result["actual_status"] is not None for result in run["results"])


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
