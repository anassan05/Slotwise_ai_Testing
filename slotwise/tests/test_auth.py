from app import create_app
from database import get_connection


def make_client(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": str(tmp_path / "auth.db")})
    return app, app.test_client()


def test_register_creates_hashed_user_and_session(tmp_path):
    app, client = make_client(tmp_path)

    response = client.post(
        "/api/auth/register",
        json={"full_name": "Avery Morgan", "email": "AVERY@example.com", "password": "secure-pass-123"},
    )

    assert response.status_code == 201
    assert response.get_json()["user"]["email"] == "avery@example.com"
    with client.session_transaction() as session:
        assert session["user_id"] == 1
    with get_connection(app.config["DATABASE"]) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE email = ?", ("avery@example.com",)).fetchone()
    assert row["password_hash"] != "secure-pass-123"


def test_register_rejects_duplicate_and_weak_accounts(tmp_path):
    _, client = make_client(tmp_path)
    valid = {"full_name": "Avery Morgan", "email": "avery@example.com", "password": "secure-pass-123"}

    assert client.post("/api/auth/register", json=valid).status_code == 201
    duplicate = client.post("/api/auth/register", json=valid)
    weak = client.post("/api/auth/register", json={**valid, "email": "new@example.com", "password": "short"})

    assert duplicate.status_code == 409
    assert weak.status_code == 400


def test_login_and_logout_manage_session(tmp_path):
    _, client = make_client(tmp_path)
    credentials = {"full_name": "Avery Morgan", "email": "avery@example.com", "password": "secure-pass-123"}
    client.post("/api/auth/register", json=credentials)
    client.post("/api/auth/logout")

    invalid = client.post("/api/auth/login", json={"email": credentials["email"], "password": "wrong-password"})
    valid = client.post("/api/auth/login", json={"email": credentials["email"], "password": credentials["password"]})
    current = client.get("/api/auth/me")
    client.post("/api/auth/logout")
    signed_out = client.get("/api/auth/me")

    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert current.get_json()["authenticated"] is True
    assert signed_out.get_json()["authenticated"] is False


def test_auth_pages_render(tmp_path):
    _, client = make_client(tmp_path)

    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200
