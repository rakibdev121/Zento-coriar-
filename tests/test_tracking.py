from tests.conftest import parcel_payload


def test_public_tracking_hides_personal_details(client, auth_headers):
    p = client.post("/api/parcels", json=parcel_payload(), headers=auth_headers).json()
    r = client.get(f"/api/track/{p['tracking_number'].lower()}")  # case-insensitive, no auth
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "booked" and body["delivery_city"] == "Lakeview"
    text = r.text
    for secret in ("Daniel Okoye", "Amina Rahman", "88 Cedar Avenue", "555 010", "amina@example.com", "price"):
        assert secret not in text


def test_tracking_not_found_and_malformed(client):
    assert client.get("/api/track/ZNT222222222").status_code == 404
    assert client.get("/api/track/hello").status_code == 422


def test_health_and_unknown_api_route(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/does-not-exist").status_code == 404
