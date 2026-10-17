import os

# Must be set before the app is imported. In-memory SQLite keeps tests fast and self-contained.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
os.environ["CURRENCY"] = "USD"
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import login_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_limiter.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


USER = {"full_name": "Amina Rahman", "email": "amina@example.com", "phone": "+1 555 010 2030", "password": "correct-horse-42"}


def register(client, **overrides):
    return client.post("/api/auth/register", json={**USER, **overrides})


@pytest.fixture
def auth_headers(client):
    token = register(client).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def parcel_payload(**overrides):
    base = {
        "sender_name": "Amina Rahman", "sender_phone": "+1 555 010 2030",
        "pickup_address": "12 Harbour Road", "pickup_city": "Lakeview",
        "recipient_name": "Daniel Okoye", "recipient_phone": "+1 555 010 4455",
        "delivery_address": "88 Cedar Avenue", "delivery_city": "Lakeview",
        "zone": "local", "service": "standard", "weight_kg": "2.5", "declared_value": "100", "fragile": True,
    }
    return {**base, **overrides}
