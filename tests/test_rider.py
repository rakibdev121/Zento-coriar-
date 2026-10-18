import base64
from decimal import Decimal

from app.rider_logic import commission_for
from tests.conftest import parcel_payload, register
from tests.test_admin import book, make_admin

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


def apply_payload(**kw):
    base = {"full_name": "Rahim Uddin", "email": "rahim@example.com", "phone": "+880 1900 000000", "password": "rider-pass-42", "city": "Mirpur",
            "vehicle": "bike", "id_type": "nid", "id_number": "1234567890", "photo": PNG, "id_document": PNG}
    return {**base, **kw}


def apply_rider(client, **kw):
    r = client.post("/api/rider/apply", json=apply_payload(**kw))
    assert r.status_code == 201, r.text
    return r.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def approved_rider(client, admin, **kw):
    data = apply_rider(client, **kw)
    assert client.post(f"/api/admin/riders/{data['rider']['id']}/approve", headers=admin).status_code == 200
    return bearer(data["access_token"]), data["rider"]["id"]


def assign(client, admin, parcel_id, rider_id):
    r = client.patch(f"/api/admin/parcels/{parcel_id}", json={"rider_id": rider_id}, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def test_commission_is_twenty_percent_rounded():
    assert commission_for("15.55") == Decimal("3.11")
    assert commission_for("100") == Decimal("20.00")


def test_pending_rider_can_sign_in_but_not_work(client):
    data = apply_rider(client)
    assert data["rider"]["status"] == "pending"
    h = bearer(data["access_token"])
    assert client.get("/api/rider/me", headers=h).json()["status"] == "pending"
    assert client.get("/api/rider/dashboard", headers=h).status_code == 403
    assert client.post("/api/auth/login", json={"email": "rahim@example.com", "password": "rider-pass-42"}).status_code == 200


def test_apply_validation(client):
    r = client.post("/api/rider/apply", json=apply_payload(photo="not-an-image"))
    assert r.status_code == 422 and any(e["field"] == "photo" for e in r.json()["errors"])
    wrong_type = "data:image/jpeg;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
    assert client.post("/api/rider/apply", json=apply_payload(id_document=wrong_type)).status_code == 422
    assert client.post("/api/rider/apply", json=apply_payload(id_number="12")).status_code == 422
    apply_rider(client)
    assert client.post("/api/rider/apply", json=apply_payload()).status_code == 409  # same email


def test_admin_reviews_application_and_documents(client):
    admin = make_admin(client)
    rider_h = bearer(apply_rider(client)["access_token"])
    riders = client.get("/api/admin/riders", headers=admin).json()["items"]
    app_ = next(r for r in riders if r["email"] == "rahim@example.com")
    assert app_["status"] == "pending" and app_["is_active"] is False and app_["id_number"] == "1234567890"
    doc = client.get(f"/api/admin/riders/{app_['id']}/documents/id_document", headers=admin)
    assert doc.status_code == 200 and doc.headers["content-type"] == "image/png" and doc.content.startswith(b"\x89PNG")
    assert client.get(f"/api/admin/riders/{app_['id']}/documents/photo", headers=rider_h).status_code == 403  # admins only
    # rejection needs a reason and only works on pending applications
    assert client.post(f"/api/admin/riders/{app_['id']}/reject", json={"reason": ""}, headers=admin).status_code == 422
    r = client.post(f"/api/admin/riders/{app_['id']}/reject", json={"reason": "Photo is blurry"}, headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    me = client.get("/api/rider/me", headers=rider_h).json()
    assert me["status"] == "rejected" and me["reject_reason"] == "Photo is blurry"
    assert client.get("/api/rider/dashboard", headers=rider_h).status_code == 403


def test_cannot_assign_unapproved_rider(client, auth_headers):
    admin = make_admin(client)
    rid = apply_rider(client)["rider"]["id"]
    parcel = book(client, auth_headers)
    r = client.patch(f"/api/admin/parcels/{parcel['id']}", json={"rider_id": rid}, headers=admin)
    assert r.status_code == 409
    client.post(f"/api/admin/riders/{rid}/approve", headers=admin)
    assert client.patch(f"/api/admin/parcels/{parcel['id']}", json={"rider_id": rid}, headers=admin).status_code == 200


def test_full_delivery_flow_pays_twenty_percent(client, auth_headers):
    admin = make_admin(client)
    rider_h, rid = approved_rider(client, admin)
    parcel = book(client, auth_headers)
    price = Decimal(str(parcel["price_total"]))
    detail = assign(client, admin, parcel["id"], rid)
    assert detail["rider_response"] == "pending"

    dash = client.get("/api/rider/dashboard", headers=rider_h).json()
    assert [p["id"] for p in dash["requests"]] == [parcel["id"]] and dash["active"] == []
    offer = dash["requests"][0]
    assert offer["contact"] is None  # no names or phones before accepting
    assert Decimal(offer["commission"]) == commission_for(price)
    # cannot start work before accepting
    assert client.post(f"/api/rider/parcels/{parcel['id']}/status", json={"status": "picked_up"}, headers=rider_h).status_code == 409

    acc = client.post(f"/api/rider/parcels/{parcel['id']}/respond", json={"action": "accept"}, headers=rider_h)
    assert acc.status_code == 200 and acc.json()["rider_response"] == "accepted" and acc.json()["contact"]["recipient_name"] == "Daniel Okoye"
    assert client.post(f"/api/rider/parcels/{parcel['id']}/respond", json={"action": "accept"}, headers=rider_h).status_code == 409

    step = lambda s: client.post(f"/api/rider/parcels/{parcel['id']}/status", json={"status": s}, headers=rider_h)
    assert step("delivered").status_code == 409  # cannot skip steps
    assert step("picked_up").status_code == 200
    assert step("out_for_delivery").status_code == 200
    done = step("delivered")
    assert done.status_code == 200 and done.json()["status"] == "delivered"
    assert Decimal(done.json()["commission"]) == commission_for(price)
    assert step("delivered").status_code == 409  # closed

    earn = client.get("/api/rider/earnings", headers=rider_h).json()
    assert Decimal(earn["total"]) == commission_for(price) and Decimal(earn["today"]) == commission_for(price) and earn["delivered"] == 1
    assert client.get("/api/rider/dashboard", headers=rider_h).json()["streak"] == 1

    # the customer sees the progress on public tracking, and admin sees the commission
    track = client.get(f"/api/track/{parcel['tracking_number']}").json()
    assert [e["status"] for e in track["events"]][-1] == "delivered"
    assert Decimal(client.get(f"/api/admin/parcels/{parcel['id']}", headers=admin).json()["rider_commission"]) == commission_for(price)


def test_rejecting_frees_the_parcel_for_admin(client, auth_headers):
    admin = make_admin(client)
    rider_h, rid = approved_rider(client, admin)
    parcel = book(client, auth_headers)
    assign(client, admin, parcel["id"], rid)
    r = client.post(f"/api/rider/parcels/{parcel['id']}/respond", json={"action": "reject", "reason": "Too far"}, headers=rider_h)
    assert r.status_code == 200
    detail = client.get(f"/api/admin/parcels/{parcel['id']}", headers=admin).json()
    assert detail["rider"] is None and detail["rider_response"] == "rejected" and "Too far" in detail["rider_note"]
    assert client.get("/api/rider/dashboard", headers=rider_h).json()["requests"] == []
    assert client.get(f"/api/rider/parcels?tab=requests", headers=rider_h).json()["items"] == []


def test_riders_only_see_their_own_parcels(client, auth_headers):
    admin = make_admin(client)
    h1, rid1 = approved_rider(client, admin)
    h2, _ = approved_rider(client, admin, email="second@example.com", full_name="Second Rider")
    parcel = book(client, auth_headers)
    assign(client, admin, parcel["id"], rid1)
    assert client.post(f"/api/rider/parcels/{parcel['id']}/respond", json={"action": "accept"}, headers=h2).status_code == 404
    assert client.get("/api/rider/parcels?tab=requests", headers=h2).json()["items"] == []


def test_customers_and_anonymous_cannot_use_rider_api(client, auth_headers):
    assert client.get("/api/rider/dashboard").status_code == 401
    assert client.get("/api/rider/dashboard", headers=auth_headers).status_code == 403


def test_admin_marking_delivered_also_pays_commission(client, auth_headers):
    admin = make_admin(client)
    rider_h, rid = approved_rider(client, admin)
    parcel = book(client, auth_headers)
    assign(client, admin, parcel["id"], rid)
    client.post(f"/api/rider/parcels/{parcel['id']}/respond", json={"action": "accept"}, headers=rider_h)
    for st in ("picked_up", "in_transit", "out_for_delivery", "delivered"):
        assert client.patch(f"/api/admin/parcels/{parcel['id']}", json={"status": st}, headers=admin).status_code == 200
    assert Decimal(client.get("/api/rider/earnings", headers=rider_h).json()["total"]) == commission_for(parcel["price_total"])


def test_parcel_pdfs(client, auth_headers):
    admin = make_admin(client)
    parcel = book(client, auth_headers)
    mine = client.get(f"/api/parcels/{parcel['id']}/pdf", headers=auth_headers)
    assert mine.status_code == 200 and mine.content.startswith(b"%PDF") and mine.headers["content-type"] == "application/pdf"
    assert parcel["tracking_number"] in mine.headers["content-disposition"]
    other = {"Authorization": f"Bearer {register(client, email='other@example.com').json()['access_token']}"}
    assert client.get(f"/api/parcels/{parcel['id']}/pdf", headers=other).status_code == 404
    assert client.get(f"/api/parcels/{parcel['id']}/pdf").status_code == 401
    assert client.get(f"/api/admin/parcels/{parcel['id']}/pdf", headers=auth_headers).status_code == 403
    adm = client.get(f"/api/admin/parcels/{parcel['id']}/pdf", headers=admin)
    assert adm.status_code == 200 and adm.content.startswith(b"%PDF")


def test_rider_page_is_served(client):
    r = client.get("/rider")
    assert r.status_code == 200 and "ZENTO" in r.text
