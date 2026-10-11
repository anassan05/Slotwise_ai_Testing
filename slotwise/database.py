import os
import sqlite3
from contextlib import contextmanager
from contextlib import suppress
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "slotwise.db"
ACTIVE_STATUSES = ("BOOKED",)


class SlotWiseConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def get_db_path() -> str:
    return os.environ.get("SLOTWISE_DB", str(DEFAULT_DB_PATH))


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(
        db_path or get_db_path(),
        timeout=30,
        isolation_level=None,
        factory=SlotWiseConnection,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(db_path: str | None = None, immediate: bool = False):
    conn = get_connection(db_path)
    began = False
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        began = True
        yield conn
        conn.commit()
    except Exception:
        if began:
            with suppress(sqlite3.Error):
                conn.rollback()
        raise
    finally:
        conn.close()


def is_lock_error(error: sqlite3.Error) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def init_db(db_path: str | None = None) -> None:
    path = Path(db_path or get_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)

    with transaction(str(path), immediate=True) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                patient_name TEXT NOT NULL DEFAULT '',
                mobile_number TEXT NOT NULL DEFAULT '',
                email TEXT,
                doctor_id TEXT NOT NULL DEFAULT '',
                doctor_name TEXT NOT NULL DEFAULT '',
                service TEXT NOT NULL DEFAULT 'Consultation',
                service_id TEXT NOT NULL DEFAULT '',
                appointment_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL DEFAULT '09:30',
                status TEXT NOT NULL DEFAULT 'BOOKED',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                cancelled_at TEXT
            )
            """
        )

        columns = _columns(conn, "appointments")
        migrations = {
            "patient_name": "ALTER TABLE appointments ADD COLUMN patient_name TEXT NOT NULL DEFAULT ''",
            "mobile_number": "ALTER TABLE appointments ADD COLUMN mobile_number TEXT NOT NULL DEFAULT ''",
            "email": "ALTER TABLE appointments ADD COLUMN email TEXT",
            "doctor_id": "ALTER TABLE appointments ADD COLUMN doctor_id TEXT NOT NULL DEFAULT ''",
            "doctor_name": "ALTER TABLE appointments ADD COLUMN doctor_name TEXT NOT NULL DEFAULT ''",
            "service": "ALTER TABLE appointments ADD COLUMN service TEXT NOT NULL DEFAULT 'Consultation'",
            "service_id": "ALTER TABLE appointments ADD COLUMN service_id TEXT NOT NULL DEFAULT ''",
            "end_time": "ALTER TABLE appointments ADD COLUMN end_time TEXT NOT NULL DEFAULT '09:30'",
            "created_at": "ALTER TABLE appointments ADD COLUMN created_at TEXT",
            "updated_at": "ALTER TABLE appointments ADD COLUMN updated_at TEXT",
            "cancelled_at": "ALTER TABLE appointments ADD COLUMN cancelled_at TEXT",
        }
        for column, sql in migrations.items():
            if column not in columns:
                conn.execute(sql)
        conn.execute("UPDATE appointments SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP)")
        conn.execute("UPDATE appointments SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)")
        conn.execute("UPDATE appointments SET patient_name = customer_name WHERE patient_name = ''")
        conn.execute("UPDATE appointments SET service_id = 'legacy' WHERE service_id = ''")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                mode TEXT NOT NULL DEFAULT 'standard',
                total INTEGER NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                pass_percentage REAL NOT NULL DEFAULT 0,
                summary TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                scenario_id TEXT NOT NULL,
                name TEXT NOT NULL,
                business_rule TEXT NOT NULL,
                expected_status INTEGER NOT NULL,
                actual_status INTEGER,
                expected_result TEXT NOT NULL,
                actual_result TEXT NOT NULL,
                passed INTEGER NOT NULL,
                failure_explanation TEXT,
                checks TEXT NOT NULL DEFAULT '',
                steps TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES test_runs(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_appointments_slot
            ON appointments (appointment_date, doctor_id, start_time, end_time, status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_appointments_doctor_slot
            ON appointments (appointment_date, doctor_id, start_time, end_time, status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_test_results_run
            ON test_results (run_id)
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email)")
        result_columns = _columns(conn, "test_results")
        if "checks" not in result_columns:
            conn.execute("ALTER TABLE test_results ADD COLUMN checks TEXT NOT NULL DEFAULT ''")
        if "steps" not in result_columns:
            conn.execute("ALTER TABLE test_results ADD COLUMN steps TEXT NOT NULL DEFAULT '[]'")


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)
