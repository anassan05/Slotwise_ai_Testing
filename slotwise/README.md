# SlotWise + TestPilot

SlotWise is a Flask appointment booking app with SQLite persistence. TestPilot is a custom rule-based automated testing engine that generates scenarios from explicit business rules, executes them against the Flask backend with Flask's test client, stores real results in SQLite, and displays the history in the dashboard.

No LLM or AI API key is required. TestPilot is intentionally implemented as deterministic Python rules, with a structure that can be extended later.

## Project Structure

```text
slotwise/
  app.py
  database.py
  clinic_config.py
  templates/login.html
  templates/register.html
  requirements.txt
  slotwise.db
  templates/index.html
  static/css/style.css
  static/js/app.js
  testpilot/
    scenario_generator.py
    runner.py
    result_store.py
  tests/
    test_auth.py
    test_appointments.py
    test_testpilot.py
```

## Windows Setup

From PowerShell:

```powershell
cd D:\Slotwise_ai_Testing\slotwise
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `py -3.11` is not available, use the full path to your Python 3.11 executable.

## Run the App

```powershell
cd D:\Slotwise_ai_Testing\slotwise
.\.venv\Scripts\Activate.ps1
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

For production hosting, run the Flask application with Gunicorn instead of Flask's development server:

```powershell
gunicorn --bind 0.0.0.0:$env:PORT "app:create_app()"
```

Configure these environment variables on the hosting platform:

```text
SECRET_KEY=<long-random-secret>
SLOTWISE_DB=<persistent-path-to-slotwise.db>
SESSION_COOKIE_SECURE=1
```

The Flask service serves both the frontend templates/static assets and the REST API. Keep the SQLite path on persistent storage, or migrate to PostgreSQL for a multi-instance production deployment.

## Authentication Demo

Open `/register` to create an account or `/login` to sign in. Accounts are stored in the additive `users` SQLite table with Werkzeug password hashes and a Flask session. Authentication checks are available through `/api/auth/register`, `/api/auth/login`, `/api/auth/me`, and `/api/auth/logout`.

## Run Tests

```powershell
cd D:\Slotwise_ai_Testing\slotwise
.\.venv\Scripts\Activate.ps1
pytest -q
```

The pytest suite uses temporary SQLite databases and does not run destructive tests against `slotwise.db`.

## Five-Minute Interview Demo

1. Start the app, create an account at `/register`, sign in at `/login`, and open the operations console.
2. Create two future appointments with adjacent times. Point out the JSON request, HTTP 201 response, and the new SQLite row in the appointment list.
3. Try an overlapping time range. Explain that the REST endpoint returns HTTP 409 and that `BEGIN IMMEDIATE` serializes competing booking transactions before overlap checking.
4. Cancel the first appointment and book the same slot again. The cancelled row remains for history, while its slot is available because only `BOOKED` rows participate in overlap checks.
5. Open **TestPilot** and run the suite. Watch the browser reveal each real request, masked input, expected output, actual response, and pass/fail result one at a time. The run itself uses isolated temporary databases and completes quickly before the paced presentation.
6. Run **Defect demo**. TestPilot disables overlap validation only in an isolated `TESTING` app and temporary database, records a genuine failure, then runs the restored implementation and records a pass.

## Troubleshooting

- If imports fail during pytest collection, run commands from the `slotwise` directory, not its parent.
- If port 5000 is busy, stop the existing Flask process or start with `python -c "from app import create_app; create_app().run(port=5001)"`.
- If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process Bypass` for the current terminal or invoke `.venv\Scripts\python.exe` directly.
- Do not delete `slotwise.db`; tests create their own temporary databases and the app initializes missing tables additively.

## TestPilot Dashboard

In the browser:

1. Use **Run tests** to execute all generated business-rule scenarios.
2. Use **Defect demo** to run a controlled overlap-validation failure in an isolated test app, then run the restored validation scenario.
3. Review pass/fail counts, pass percentage, expected status, actual status and failure explanations.

The application has a separate **TestPilot QA** screen for interview demos. It shows plain-language business rules, expected versus actual outcomes, pass/fail badges, pass percentage and SQL evidence counts from the `test_runs` and `test_results` tables.

TestPilot persists run summaries in `test_runs` and detailed scenario results in `test_results`.

## Architecture Notes

- `database.py` owns SQLite connections, safe initialization and additive migrations.
- `app.py` exposes the HTML pages and JSON APIs for authentication, booking, listing, cancellation, stats and TestPilot.
- `booking_service.py` is the single source of truth for booking rules: required fields, service duration lookup, clinic hours, start-time interval validation, overlap checks, cancellation, rebooking and availability.
- Booking writes use `BEGIN IMMEDIATE` transactions and parameterized SQL to avoid duplicate active slots under concurrent requests. SQLite busy/locked write errors are returned as retryable booking errors instead of generic crashes.
- `clinic_config.py` owns the initial service catalog, service durations, clinic hours, and slot interval.
- Patient bookings submit patient name, mobile number, optional email, service ID, date, and start time. The backend retrieves the service duration and calculates `end_time`; browser-supplied end times are ignored.
- `/api/availability` generates duration-aware start slots inside clinic hours and marks slots blocked by active appointments.
- Overlap detection rejects active appointments where the requested start is before the existing end and the requested end is after the existing start.
- Cancelled appointments are excluded from overlap checks, so a cancelled slot can be booked again.
- `testpilot/scenario_generator.py` declares the business rules as scenarios.
- `testpilot/runner.py` executes scenarios with Flask's test client, checks response content and SQLite row-count invariants, and compares expected versus actual behavior.
- `testpilot/result_store.py` saves real run results to SQLite for the dashboard.

Flask serves the dashboard and REST API routes. SQLite stores appointments and TestPilot evidence using parameterized SQL and transactions. Scenario generation turns explicit Python business rules into executable cases; TestPilot then runs those cases against isolated Flask test clients and temporary SQLite files. It is a deterministic rule-based engine, not an LLM-powered service.

The clinic booking form does not ask patients for an end time. It loads services and available start slots from the backend, previews the calculated duration in the browser, and the server independently validates the service, clinic hours, slot interval, and overlap before inserting the appointment.

Current MVP limitation: doctor-specific schedules are not implemented because the schema does not yet include doctors. Conflict checks are clinic-wide. If doctors are added later, add a `doctor_id` column through a safe migration and include it in availability and overlap queries.
