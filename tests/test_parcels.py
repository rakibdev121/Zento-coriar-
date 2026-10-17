from tests.conftest import parcel_payload, register


def book(client, headers, **overrides):
    return client.post("/api/parcels", json=parcel_payload(**overrides), headers=headers)


def test_quote_endpoint_is_public_and_validates(client):
    ok = client.post("/api/pricing/quote", json={"zone": "local", "service": "standard", "weight_kg": "1"})
    assert ok.status_code == 200 and ok.json()["total"] == "5.00" and ok.json()["currency"] == "USD"
    bad = client.post("/api/pricing/quote", json={"zone": "regional", "service": "same_day", "weight_kg": "1"})
    assert bad.status_code == 422
    assert client.post("/api/pricing/quote", json={"zone": "local", "service": "standard", "weight_kg": "99"}).status_code == 422


def test_pricing_options(client):
    body = client.get("/api/pricing/options").json()
    assert {z["id"] for z in body["zones"]} == {"local", "regional", "national"}


def test_booking_requires_auth(client):
    assert client.post("/api/parcels", json=parcel_payload()).status_code == 401


def test_booking_creates_parcel_with_server_side_price(client, auth_headers):
    r = book(client, auth_headers)
    assert r.status_code == 201
    p = r.json()
    assert p["tracking_number"].startswith("ZNT") and p["status"] == "booked"
    # base 5.00 + extra 1.5kg * 1.00 + fragile 2.00 + insurance 1.50 = 10.00
    assert p["price_total"] == "10.00"
    assert [e["status"] for e in p["events"]] == ["booked"]


def test_booking_validation(client, auth_headers):
    r = book(client, auth_headers, recipient_phone="x", weight_kg="0", zone="regional", service="same_day")
    assert r.status_code == 422
    assert {"recipient_phone", "weight_kg"} <= {e["field"] for e in r.json()["errors"]}


def test_extra_client_supplied_price_is_ignored(client, auth_headers):
    p = book(client, auth_headers, price_total="0.01").json()
    assert p["price_total"] == "10.00"


def test_list_get_and_isolation_between_users(client, auth_headers):
    mine = book(client, auth_headers).json()
    book(client, auth_headers)
    page = client.get("/api/parcels?page_size=1", headers=auth_headers).json()
    assert page["total"] == 2 and len(page["items"]) == 1

    other = {"Authorization": "Bearer " + register(client, email="other@example.com").json()["access_token"]}
    assert client.get("/api/parcels", headers=other).json()["total"] == 0
    assert client.get(f"/api/parcels/{mine['id']}", headers=other).status_code == 404
    assert client.post(f"/api/parcels/{mine['id']}/cancel", headers=other).status_code == 404
    assert client.get(f"/api/parcels/{mine['id']}", headers=auth_headers).status_code == 200


def test_list_status_filter_and_bad_params(client, auth_headers):
    book(client, auth_headers)
    assert client.get("/api/parcels?status=delivered", headers=auth_headers).json()["total"] == 0
    assert client.get("/api/parcels?status=booked", headers=auth_headers).json()["total"] == 1
    assert client.get("/api/parcels?status=bogus", headers=auth_headers).status_code == 422
    assert client.get("/api/parcels?page=0", headers=auth_headers).status_code == 422


def test_cancel_flow(client, auth_headers):
    p = book(client, auth_headers).json()
    r = client.post(f"/api/parcels/{p['id']}/cancel", headers=auth_headers)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert [e["status"] for e in r.json()["events"]] == ["booked", "cancelled"]
    assert client.post(f"/api/parcels/{p['id']}/cancel", headers=auth_headers).status_code == 409


def test_dashboard_summary(client, auth_headers):
    a = book(client, auth_headers).json()
    book(client, auth_headers)
    client.post(f"/api/parcels/{a['id']}/cancel", headers=auth_headers)
    s = client.get("/api/dashboard/summary", headers=auth_headers).json()
    assert (s["total_parcels"], s["in_progress"], s["cancelled"], s["delivered"]) == (2, 1, 1, 0)
    assert s["total_spent"] == "10.00" and len(s["recent"]) == 2
