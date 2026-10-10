from __future__ import annotations

import json

from database import get_connection, init_db, transaction


class ResultStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path
        init_db(db_path)

    def store_run(self, run: dict) -> int:
        with transaction(self.db_path, immediate=True) as conn:
            cursor = conn.execute(
                """
                INSERT INTO test_runs
                    (started_at, finished_at, mode, total, passed, failed, pass_percentage, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["started_at"],
                    run["finished_at"],
                    run["mode"],
                    run["total"],
                    run["passed"],
                    run["failed"],
                    run["pass_percentage"],
                    run["summary"],
                ),
            )
            run_id = cursor.lastrowid
            for result in run["results"]:
                conn.execute(
                    """
                    INSERT INTO test_results
                        (run_id, scenario_id, name, business_rule, expected_status, actual_status,
                         expected_result, actual_result, passed, failure_explanation, checks, steps)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        result["scenario_id"],
                        result["name"],
                        result["business_rule"],
                        result["expected_status"],
                        result["actual_status"],
                        result["expected_result"],
                        result["actual_result"],
                        1 if result["passed"] else 0,
                        result["failure_explanation"],
                        result.get("checks", ""),
                        json.dumps(result.get("steps", [])),
                    ),
                )
            return run_id

    def history(self, limit: int = 10) -> list[dict]:
        with get_connection(self.db_path) as conn:
            runs = conn.execute(
                """
                SELECT *
                FROM test_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            history = []
            for run in runs:
                results = conn.execute(
                    """
                    SELECT scenario_id, name, business_rule, expected_status, actual_status,
                           expected_result, actual_result, passed, failure_explanation, checks, steps
                    FROM test_results
                    WHERE run_id = ?
                    ORDER BY id
                    """,
                    (run["id"],),
                ).fetchall()
                item = dict(run)
                item["results"] = []
                for result in results:
                    item["results"].append(
                        dict(result)
                        | {
                            "passed": bool(result["passed"]),
                            "steps": json.loads(result["steps"] or "[]"),
                        }
                    )
                history.append(item)
        return history
