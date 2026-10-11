from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app import create_app
from database import get_connection
from testpilot.scenario_generator import Scenario, generate_defect_overlap_scenario, generate_scenarios


def run_scenarios(scenarios: list[Scenario] | None = None, app_config: dict | None = None, mode: str = "standard") -> dict:
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    results = []

    for scenario in scenarios or generate_scenarios():
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "slotwise_test.db")
            config = {"TESTING": True, "DATABASE": db_path}
            if app_config:
                config.update({key: value for key, value in app_config.items() if key != "DATABASE"})
            config["DATABASE"] = db_path
            app = create_app(config)
            with app.test_client() as client:
                results.append(_execute_scenario(client, scenario))

    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    failed = total - passed
    return {
        "mode": mode,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_percentage": round((passed / total) * 100, 2) if total else 0,
        "summary": f"{passed}/{total} scenarios passed.",
        "results": results,
    }


def run_defect_demonstration() -> dict:
    scenario = generate_defect_overlap_scenario()
    defective = run_scenarios(
        [scenario],
        app_config={"DISABLE_OVERLAP_VALIDATION_FOR_DEMO": True},
        mode="defect-demo: overlap validation disabled",
    )
    restored = run_scenarios([scenario], mode="defect-demo: restored validation")
    return {"defective": defective, "restored": restored}


def _execute_scenario(client, scenario: Scenario) -> dict:
    context: dict[str, dict] = {}
    last_response = None
    failed_assertions = []
    semantic_result = None
    execution_steps = []
    starting_counts = _database_counts(client, scenario.expected_database_changes)

    for step in scenario.steps:
        request_path = _format_path(step["path"], context)
        response = _request(client, step, context)
        body = response.get_json(silent=True) or {}
        last_response = response
        execution_steps.append(
            {
                "method": step["method"].upper(),
                "path": request_path,
                "input": _safe_input(step.get("json") or {}),
                "actual_status": response.status_code,
                "response": body.get("error") or body.get("message") or "JSON response received",
            }
        )

        if step.get("save_as") and body.get("appointment"):
            context[step["save_as"]] = body["appointment"]

        if step.get("save_count_as"):
            context[step["save_count_as"]] = {"count": len(body.get("appointments", []))}

        if step.get("save_db_count_as"):
            context[step["save_db_count_as"]] = {"count": _appointment_count(client)}

        if step.get("expect_error_contains"):
            error_text = body.get("error", "")
            if step["expect_error_contains"].lower() not in error_text.lower():
                failed_assertions.append(
                    f"Expected error text containing '{step['expect_error_contains']}', got '{error_text}'."
                )

        if step.get("assert_contains_saved"):
            saved = context[step["assert_contains_saved"]]
            appointment_ids = {item["id"] for item in body.get("appointments", [])}
            if saved["id"] not in appointment_ids:
                failed_assertions.append(f"Expected appointment id {saved['id']} to be listed.")

        if step.get("assert_count_unchanged"):
            before = context[step["assert_count_unchanged"]]["count"]
            after = len(body.get("appointments", []))
            if before != after:
                failed_assertions.append(f"Expected {before} appointments after invalid request, found {after}.")

        if step.get("assert_db_count_unchanged"):
            before = context[step["assert_db_count_unchanged"]]["count"]
            after = _appointment_count(client)
            if before != after:
                failed_assertions.append(f"Expected SQLite appointment count {before}, found {after}.")

        if step.get("assert_result"):
            semantic_result = step["assert_result"]

    actual_status = last_response.status_code if last_response else None
    actual_body = last_response.get_json(silent=True) if last_response else {}
    actual_result = semantic_result or _actual_result(actual_status, actual_body)
    if actual_status != scenario.expected_status:
        failed_assertions.append(f"Expected HTTP {scenario.expected_status}, got HTTP {actual_status}.")
    if actual_result != scenario.expected_result:
        failed_assertions.append(f"Expected result '{scenario.expected_result}', got '{actual_result}'.")
    failed_assertions.extend(_evaluate_response_conditions(actual_body, scenario.expected_response_conditions))
    failed_assertions.extend(_evaluate_database_changes(client, starting_counts, scenario.expected_database_changes))
    if execution_steps:
        execution_steps[-1]["expected_status"] = scenario.expected_status
        execution_steps[-1]["expected_result"] = scenario.expected_result
        execution_steps[-1]["actual_result"] = actual_result

    passed = not failed_assertions
    explanation = None
    if not passed:
        explanation = " ".join(failed_assertions)

    return {
        "scenario_id": scenario.id,
        "name": scenario.name,
        "business_rule": scenario.business_rule,
        "expected_status": scenario.expected_status,
        "actual_status": actual_status,
        "expected_result": scenario.expected_result,
        "actual_result": actual_result,
        "passed": passed,
        "failure_explanation": explanation,
        "checks": _checks_for_scenario(scenario),
        "steps": execution_steps,
    }


def _checks_for_scenario(scenario: Scenario) -> str:
    checks = ["HTTP status", "semantic result"]
    if scenario.expected_response_conditions:
        checks.append("response fields")
    if scenario.expected_database_changes:
        checks.append("database changes")
    if any(step.get("expect_error_contains") for step in scenario.steps):
        checks.append("response error content")
    if any(step.get("assert_contains_saved") for step in scenario.steps):
        checks.append("persistence in appointment list")
    if any(step.get("assert_count_unchanged") or step.get("assert_db_count_unchanged") for step in scenario.steps):
        checks.append("SQLite row-count change")
    return ", ".join(checks)


def _appointment_count(client) -> int:
    db_path = client.application.config["DATABASE"]
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]


def _database_counts(client, changes: list[dict]) -> dict[str, int]:
    tables = {change["table"] for change in changes}
    if not tables:
        return {}
    db_path = client.application.config["DATABASE"]
    with get_connection(db_path) as conn:
        return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def _evaluate_database_changes(client, starting_counts: dict[str, int], changes: list[dict]) -> list[str]:
    failures = []
    if not changes:
        return failures
    current_counts = _database_counts(client, changes)
    for change in changes:
        table = change["table"]
        expected_delta = change["delta"]
        actual_delta = current_counts[table] - starting_counts[table]
        if actual_delta != expected_delta:
            failures.append(f"Expected {table} row delta {expected_delta}, got {actual_delta}.")
    return failures


def _evaluate_response_conditions(body: dict, conditions: list[dict]) -> list[str]:
    failures = []
    for condition in conditions:
        value = _get_path(body, condition["path"])
        if "equals" in condition and value != condition["equals"]:
            failures.append(f"Expected response {condition['path']} to equal {condition['equals']!r}, got {value!r}.")
        if "contains" in condition and condition["contains"].lower() not in str(value or "").lower():
            failures.append(f"Expected response {condition['path']} to contain {condition['contains']!r}, got {value!r}.")
    return failures


def _get_path(body: dict, path: str):
    current = body
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _safe_input(payload: dict) -> dict:
    return {
        key: "********" if "password" in key.lower() else value
        for key, value in payload.items()
    }


def _request(client, step: dict, context: dict):
    path = _format_path(step["path"], context)
    method = step["method"].upper()
    if method == "GET":
        return client.get(path)
    if method == "POST":
        return client.post(path, json=step.get("json"))
    raise ValueError(f"Unsupported scenario method: {method}")


def _format_path(path: str, context: dict) -> str:
    for name, value in context.items():
        if isinstance(value, dict) and "id" in value:
            path = path.replace("{" + name + ".id}", str(value["id"]))
    return path


def _actual_result(status: int | None, body: dict) -> str:
    if status == 201 and "user" in body:
        return "registered"
    if status == 200 and body.get("authenticated") is True:
        return "authenticated"
    if status == 201:
        return "created"
    if status == 200 and body.get("appointment", {}).get("status") == "CANCELLED":
        return "cancelled"
    if status == 200 and "appointments" in body:
        return "listed"
    if status == 400:
        return "validation_error"
    if status == 409:
        return "conflict"
    if status == 404:
        return "not_found"
    if status == 401:
        return "authentication_error"
    return body.get("error") or "unknown"
