from sqlalchemy import select

from app.database import SessionLocal
from app.models import User
from tests.conftest import USER, fund, parcel_payload, register


def make_admin(client, email="boss@example.com"):
    token = register(client, email=email, full_name="Rakib Hasan").json()["access_token"]
    with SessionLocal() as db:
        db.scalar(select(User).where(User.email == email)).is_admin = True
        db.commit()
    return {"Authorization": f"Bearer {token}"}


def book(client, headers, **kw):
    fund(client, headers, "10000")  # bookings are paid from the wallet
    r = client.post("/api/parcels", json=parcel_payload(**kw), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_admin_routes_require_admin(client, auth_headers):
    assert client.get("/api/admin/dashboard").status_code == 401
    assert client.get("/api/admin/dashboard", headers=auth_headers).status_code == 403
    assert client.get("/api/admin/parcels", headers=auth_headers).status_code == 403


def test_me_reports_admin_flag(client):
    h = make_admin(client)
    assert client.get("/api/auth/me", headers=h).json()["is_admin"] is True


def test_admin_page_is_served(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "ZENTO" in r.text


def test_dashboard_counts_and_activity(client, auth_headers):
    admin = make_admin(client)
    book(client, auth_headers)
    d = client.get("/api/admin/dashboard", headers=admin).json()
    assert d["stats"]["total_parcels"]["value"] == 1
    assert d["stats"]["active_customers"]["value"] == 1  # the admin is not counted as a customer
    assert len(d["chart"]) == 7 and sum(x["pending"] for x in d["chart"]) == 1
    assert d["recent_parcels"][0]["customer_name"] == USER["full_name"]
    assert {a["title"] for a in d["activities"]} >= {"New Booking", "Customer Registered"}


def test_status_flow_assignment_and_tracking(client, auth_headers):
    admin = make_admin(client)
    parcel = book(client, auth_headers)
    rider = client.post("/api/admin/riders", headers=admin, json={"full_name": "Arafat Ahmed", "phone": "+880 1700 000000", "vehicle": "bike"}).json()
    provider = client.post("/api/admin/providers", headers=admin, json={"name": "Pathao"}).json()

    url = f"/api/admin/parcels/{parcel['id']}"
    r = client.patch(url, headers=admin, json={"rider_id": rider["id"], "provider_id": provider["id"], "status": "picked_up", "location": "Dhaka"})
    assert r.status_code == 200 and r.json()["rider"]["name"] == "Arafat Ahmed" and r.json()["status"] == "picked_up"
    # backwards moves are rejected
    assert client.patch(url, headers=admin, json={"status": "booked"}).status_code == 409
    assert client.patch(url, headers=admin, json={"status": "delivered"}).status_code == 200
    assert client.patch(url, headers=admin, json={"status": "cancelled"}).status_code == 409
    # customer and public tracking both see the new status
    assert client.get(f"/api/parcels/{parcel['id']}", headers=auth_headers).json()["status"] == "delivered"
    pub = client.get(f"/api/track/{parcel['tracking_number']}").json()
    assert [e["status"] for e in pub["events"]] == ["booked", "picked_up", "delivered"]
    assert "Arafat" not in str(pub)
    titles = {a["title"] for a in client.get("/api/admin/dashboard", headers=admin).json()["activities"]}
    assert "Parcel Delivered" in titles
    assert client.get("/api/admin/dashboard", headers=admin).json()["providers"] == [{"name": "Pathao", "share": 100}]


def test_cannot_assign_inactive_rider(client, auth_headers):
    admin = make_admin(client)
    parcel = book(client, auth_headers)
    rider = client.post("/api/admin/riders", headers=admin, json={"full_name": "Sleepy Rider", "phone": "+880 1700 000001", "is_active": False}).json()
    r = client.patch(f"/api/admin/parcels/{parcel['id']}", headers=admin, json={"rider_id": rider["id"]})
    assert r.status_code == 409


def test_search_filter_and_csv_export(client, auth_headers):
    admin = make_admin(client)
    p = book(client, auth_headers, recipient_name="=cmd|calc")
    book(client, auth_headers)
    found = client.get("/api/admin/parcels", headers=admin, params={"q": p["tracking_number"][:8]}).json()
    assert found["total"] >= 1
    assert client.get("/api/admin/parcels", headers=admin, params={"status": "delivered"}).json()["total"] == 0
    assert client.get("/api/admin/parcels", headers=admin, params={"status": "bogus"}).status_code == 422
    csv_text = client.get("/api/admin/parcels/export.csv", headers=admin).text
    assert csv_text.startswith("Tracking,") and p["tracking_number"] in csv_text


def test_admin_creates_booking_for_customer(client, auth_headers):
    admin = make_admin(client)
    cust = client.get("/api/admin/customers", headers=admin).json()["items"][0]
    fund(client, auth_headers, "1000")  # the booking is paid from the customer's wallet
    r = client.post("/api/admin/bookings", headers=admin, json={**parcel_payload(), "user_id": cust["id"]})
    assert r.status_code == 201 and r.json()["customer_email"] == USER["email"]
    assert client.get("/api/admin/customers", headers=admin).json()["items"][0]["parcels"] == 1


def test_customer_management(client, auth_headers):
    admin = make_admin(client)
    new = client.post("/api/admin/customers", headers=admin, json={"full_name": "Md. Rifat Islam", "email": "rifat@example.com", "phone": "+880 1700 111111", "password": "pass12345"})
    assert new.status_code == 201
    assert client.post("/api/admin/customers", headers=admin, json={"full_name": "Md. Rifat Islam", "email": "rifat@example.com", "phone": "+880 1700 111111", "password": "pass12345"}).status_code == 409
    assert client.patch(f"/api/admin/customers/{new.json()['id']}", headers=admin, json={"is_active": False}).json()["is_active"] is False
    login = client.post("/api/auth/login", json={"email": "rifat@example.com", "password": "pass12345"})
    assert login.status_code == 401  # suspended accounts cannot sign in


def test_providers_areas_pricing_reports_notifications(client, auth_headers):
    admin = make_admin(client)
    book(client, auth_headers)
    assert client.post("/api/admin/providers", headers=admin, json={"name": "RedX", "website": "javascript:alert(1)"}).status_code == 422
    assert client.post("/api/admin/providers", headers=admin, json={"name": "RedX", "website": "https://redx.com.bd"}).status_code == 201
    assert client.post("/api/admin/providers", headers=admin, json={"name": "RedX"}).status_code == 409
    area = client.post("/api/admin/areas", headers=admin, json={"city": "Dhaka", "region": "Dhaka"}).json()
    assert client.get("/api/admin/areas", headers=admin).json()["items"][0]["city"] == "Dhaka"
    assert client.delete(f"/api/admin/areas/{area['id']}", headers=admin).status_code == 204
    pr = client.get("/api/admin/pricing", headers=admin).json()
    assert pr["zones"][0]["id"] == "local" and pr["fees"]["fragile"] == "20.00"
    rep = client.get("/api/admin/reports", headers=admin, params={"days": 7}).json()
    assert rep["totals"]["parcels"] == 1 and len(rep["daily"]) == 7
    assert client.get("/api/admin/notifications", headers=admin).json()["items"]


def test_change_password(client):
    admin = make_admin(client)
    bad = client.post("/api/admin/change-password", headers=admin, json={"current_password": "nope", "new_password": "newpass123"})
    assert bad.status_code == 400
    ok = client.post("/api/admin/change-password", headers=admin, json={"current_password": USER["password"], "new_password": "newpass123"})
    assert ok.status_code == 204
    assert client.post("/api/auth/login", json={"email": "boss@example.com", "password": "newpass123"}).status_code == 200
