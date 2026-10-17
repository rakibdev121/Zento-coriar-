from tests.conftest import USER, register


def test_register_returns_token_and_user(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == USER["email"] and "password" not in str(body)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()["email"] == USER["email"]


def test_register_normalises_email_and_rejects_duplicates(client):
    assert register(client, email="Amina@Example.com").status_code == 201
    r = register(client, email="amina@example.COM")
    assert r.status_code == 409


def test_register_validation_errors_are_field_level(client):
    r = register(client, password="short", phone="abc", email="nope")
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["errors"]}
    assert {"password", "phone", "email"} <= fields


def test_password_needs_letter_and_digit(client):
    assert register(client, password="onlyletters").status_code == 422
    assert register(client, password="12345678").status_code == 422


def test_login_success_and_failure(client):
    register(client)
    ok = client.post("/api/auth/login", json={"email": USER["email"], "password": USER["password"]})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/api/auth/login", json={"email": USER["email"], "password": "nope-nope-1"})
    assert bad.status_code == 401
    unknown = client.post("/api/auth/login", json={"email": "who@example.com", "password": "nope-nope-1"})
    assert unknown.status_code == 401 and unknown.json()["detail"] == bad.json()["detail"]


def test_login_rate_limit(client):
    register(client)
    for _ in range(5):
        client.post("/api/auth/login", json={"email": USER["email"], "password": "wrong-pass-1"})
    r = client.post("/api/auth/login", json={"email": USER["email"], "password": USER["password"]})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_protected_routes_require_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/parcels", headers={"Authorization": "Bearer garbage"}).status_code == 401
