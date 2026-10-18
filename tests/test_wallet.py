from decimal import Decimal

from tests.conftest import fund, parcel_payload, register, set_balance
from tests.test_admin import make_admin
from tests.test_rider import approved_rider, assign, bearer

PRICE = Decimal("132.50")  # tests.conftest.parcel_payload() under the default price list
DEPOSIT = {"amount": "500", "method": "bkash", "account": "01712345678", "reference": "TRX12345AB"}


def wallet(client, headers):
    return client.get("/api/wallet", headers=headers).json()


def book_raw(client, headers, **kw):
    return client.post("/api/parcels", json=parcel_payload(**kw), headers=headers)


def user_id(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


# ---------------- deposit ----------------
def test_new_account_starts_with_empty_wallet(client, auth_headers):
    w = wallet(client, auth_headers)
    assert w["balance"] == "0.00" and w["cod_due"] == "0.00" and w["withdrawable"] == "0.00" and w["currency"] == "BDT"


def test_deposit_needs_admin_approval(client, auth_headers):
    admin = make_admin(client)
    r = client.post("/api/wallet/deposit", json=DEPOSIT, headers=auth_headers)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert wallet(client, auth_headers)["balance"] == "0.00"  # nothing yet

    assert client.post(f"/api/admin/wallet/requests/{r.json()['id']}/approve", headers=auth_headers).status_code == 403
    ok = client.post(f"/api/admin/wallet/requests/{r.json()['id']}/approve", headers=admin)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    w = wallet(client, auth_headers)
    assert w["balance"] == "500.00" and w["transactions"][0]["kind"] == "deposit"
    # approving twice must not pay twice
    assert client.post(f"/api/admin/wallet/requests/{r.json()['id']}/approve", headers=admin).status_code == 409
    assert wallet(client, auth_headers)["balance"] == "500.00"


def test_deposit_validation(client, auth_headers):
    bad_number = client.post("/api/wallet/deposit", json={**DEPOSIT, "account": "12345"}, headers=auth_headers)
    assert bad_number.status_code == 422
    assert client.post("/api/wallet/deposit", json={**DEPOSIT, "amount": "10"}, headers=auth_headers).status_code == 409  # below minimum
    assert client.post("/api/wallet/deposit", json={**DEPOSIT, "reference": ""}, headers=auth_headers).status_code == 409
    assert client.post("/api/wallet/deposit", json={**DEPOSIT, "method": "cash"}, headers=auth_headers).status_code == 409
    assert client.post("/api/wallet/deposit", json=DEPOSIT, headers=auth_headers).status_code == 201
    assert client.post("/api/wallet/deposit", json=DEPOSIT, headers=auth_headers).status_code == 409  # same TrxID twice


def test_rejected_deposit_adds_nothing(client, auth_headers):
    admin = make_admin(client)
    rid = client.post("/api/wallet/deposit", json=DEPOSIT, headers=auth_headers).json()["id"]
    assert client.post(f"/api/admin/wallet/requests/{rid}/reject", json={"reason": "TrxID not found"}, headers=admin).status_code == 200
    assert wallet(client, auth_headers)["balance"] == "0.00"
    assert wallet(client, auth_headers)["requests"][0]["admin_note"] == "TrxID not found"


# ---------------- booking ----------------
def test_booking_is_paid_from_wallet_and_refused_without_money(client, auth_headers):
    r = book_raw(client, auth_headers)
    assert r.status_code == 409 and "Deposit" in r.json()["detail"]
    assert client.get("/api/parcels", headers=auth_headers).json()["total"] == 0  # no parcel without payment

    fund(client, auth_headers, "200")
    ok = book_raw(client, auth_headers)
    assert ok.status_code == 201
    w = wallet(client, auth_headers)
    assert Decimal(w["balance"]) == Decimal("200") - PRICE
    assert w["transactions"][0]["kind"] == "booking" and Decimal(w["transactions"][0]["amount"]) == -PRICE


def test_cancel_refunds_once(client, auth_headers):
    fund(client, auth_headers, "1000")
    p = book_raw(client, auth_headers).json()
    assert Decimal(wallet(client, auth_headers)["balance"]) == Decimal("1000") - PRICE
    assert client.post(f"/api/parcels/{p['id']}/cancel", headers=auth_headers).status_code == 200
    assert Decimal(wallet(client, auth_headers)["balance"]) == Decimal("1000")
    assert client.post(f"/api/parcels/{p['id']}/cancel", headers=auth_headers).status_code == 409
    assert Decimal(wallet(client, auth_headers)["balance"]) == Decimal("1000")


def test_admin_cancel_also_refunds(client, auth_headers):
    admin = make_admin(client)
    fund(client, auth_headers, "1000")
    p = book_raw(client, auth_headers).json()
    assert client.patch(f"/api/admin/parcels/{p['id']}", json={"status": "cancelled"}, headers=admin).status_code == 200
    assert Decimal(wallet(client, auth_headers)["balance"]) == Decimal("1000")


# ---------------- COD + rider commission ----------------
def deliver(client, rider_h, parcel_id):
    assert client.post(f"/api/rider/parcels/{parcel_id}/respond", json={"action": "accept"}, headers=rider_h).status_code == 200
    for st in ("picked_up", "out_for_delivery", "delivered"):
        r = client.post(f"/api/rider/parcels/{parcel_id}/status", json={"status": st}, headers=rider_h)
        assert r.status_code == 200, r.text


def test_cod_goes_to_customer_wallet_and_commission_to_rider(client, auth_headers):
    admin = make_admin(client)
    rider_h, rider_id = approved_rider(client, admin)
    fund(client, auth_headers, "1000")
    p = book_raw(client, auth_headers, cod_amount="500").json()
    assert p["cod_amount"] == "500.00"
    assign(client, admin, p["id"], rider_id)

    before = Decimal(wallet(client, auth_headers)["balance"])
    deliver(client, rider_h, p["id"])
    assert Decimal(wallet(client, auth_headers)["balance"]) == before + Decimal("500")  # COD credited after delivery

    rw = wallet(client, rider_h)
    assert Decimal(rw["balance"]) == (PRICE * Decimal("0.20")).quantize(Decimal("0.01"))  # 26.50 commission
    assert rw["cod_due"] == "500.00"  # the rider is holding the customer's cash
    assert rw["withdrawable"] == "0.00"  # so nothing can be withdrawn yet


def test_money_is_paid_only_once_even_if_admin_repeats_delivery(client, auth_headers):
    admin = make_admin(client)
    rider_h, rider_id = approved_rider(client, admin)
    fund(client, auth_headers, "1000")
    p = book_raw(client, auth_headers, cod_amount="300").json()
    assign(client, admin, p["id"], rider_id)
    deliver(client, rider_h, p["id"])
    cust = Decimal(wallet(client, auth_headers)["balance"])
    # delivered parcels cannot move again
    assert client.patch(f"/api/admin/parcels/{p['id']}", json={"status": "delivered"}, headers=admin).status_code in (200, 409)
    assert Decimal(wallet(client, auth_headers)["balance"]) == cust


def test_rider_cod_lock_and_release(client, auth_headers):
    """Rider holds Tk 500 COD and has Tk 1000+ in the wallet: only the free part can be withdrawn, until the COD is handed in."""
    admin = make_admin(client)
    rider_h, rider_id = approved_rider(client, admin)
    fund(client, auth_headers, "1000")
    p = book_raw(client, auth_headers, cod_amount="500").json()
    assign(client, admin, p["id"], rider_id)
    deliver(client, rider_h, p["id"])

    rider_uid = user_id(client, rider_h)
    assert client.post(f"/api/admin/wallet/users/{rider_uid}/adjust", json={"amount": "1000", "note": "old commission"}, headers=admin).status_code == 200
    w = wallet(client, rider_h)
    assert Decimal(w["balance"]) == Decimal("1026.50") and w["cod_due"] == "500.00" and Decimal(w["withdrawable"]) == Decimal("526.50")

    out = {"amount": "600", "method": "bkash", "account": "01912345678"}
    blocked = client.post("/api/wallet/withdraw", json=out, headers=rider_h)
    assert blocked.status_code == 409 and "COD" in blocked.json()["detail"]
    assert client.post("/api/wallet/withdraw", json={**out, "amount": "500"}, headers=rider_h).status_code == 201

    # hand in the cash: report it, the admin accepts, the lock opens
    handin = {"amount": "500", "method": "cash", "account": "office"}
    r = client.post("/api/wallet/cod-deposit", json=handin, headers=rider_h)
    assert r.status_code == 201 and wallet(client, rider_h)["cod_due"] == "500.00"  # not counted until accepted
    assert client.post(f"/api/admin/wallet/requests/{r.json()['id']}/approve", headers=admin).status_code == 200
    w = wallet(client, rider_h)
    assert w["cod_due"] == "0.00" and w["withdrawable"] == w["balance"] == "526.50"
    assert client.post("/api/wallet/withdraw", json={**out, "amount": "526.50"}, headers=rider_h).status_code == 201


def test_cod_deposit_limits(client, auth_headers):
    admin = make_admin(client)
    rider_h, rider_id = approved_rider(client, admin)
    handin = {"amount": "100", "method": "cash", "account": "office"}
    assert client.post("/api/wallet/cod-deposit", json=handin, headers=rider_h).status_code == 409  # owes nothing
    assert client.post("/api/wallet/cod-deposit", json=handin, headers=auth_headers).status_code == 403  # not a rider
    fund(client, auth_headers, "1000")
    p = book_raw(client, auth_headers, cod_amount="500").json()
    assign(client, admin, p["id"], rider_id)
    deliver(client, rider_h, p["id"])
    assert client.post("/api/wallet/cod-deposit", json={**handin, "amount": "600"}, headers=rider_h).status_code == 409  # more than owed
    assert client.post("/api/wallet/cod-deposit", json={**handin, "amount": "300"}, headers=rider_h).status_code == 201
    assert client.post("/api/wallet/cod-deposit", json={**handin, "amount": "300"}, headers=rider_h).status_code == 409  # 300 already waiting
    # admin can also record cash handed over at the office directly
    uid = user_id(client, rider_h)
    assert client.post(f"/api/admin/wallet/riders/{uid}/cod-receive", json={"amount": "500"}, headers=admin).status_code == 201
    assert wallet(client, rider_h)["cod_due"] == "0.00"


# ---------------- withdraw ----------------
def test_withdraw_holds_money_then_pays_or_returns_it(client, auth_headers):
    admin = make_admin(client)
    fund(client, auth_headers, "1000")
    out = {"amount": "400", "method": "nagad", "account": "01812345678"}
    r = client.post("/api/wallet/withdraw", json=out, headers=auth_headers)
    assert r.status_code == 201 and Decimal(wallet(client, auth_headers)["balance"]) == Decimal("600")  # held at once
    assert client.post(f"/api/admin/wallet/requests/{r.json()['id']}/reject", json={"reason": "wrong number"}, headers=admin).status_code == 200
    assert Decimal(wallet(client, auth_headers)["balance"]) == Decimal("1000")  # returned

    r2 = client.post("/api/wallet/withdraw", json=out, headers=auth_headers).json()
    assert client.post(f"/api/admin/wallet/requests/{r2['id']}/approve", headers=admin).status_code == 200
    assert Decimal(wallet(client, auth_headers)["balance"]) == Decimal("600")  # paid out, stays deducted


def test_withdraw_limits(client, auth_headers):
    fund(client, auth_headers, "300")
    out = {"amount": "400", "method": "bkash", "account": "01712345678"}
    assert client.post("/api/wallet/withdraw", json=out, headers=auth_headers).status_code == 409  # more than the balance
    assert client.post("/api/wallet/withdraw", json={**out, "amount": "50"}, headers=auth_headers).status_code == 409  # below minimum
    assert client.post("/api/wallet/withdraw", json={**out, "amount": "-5"}, headers=auth_headers).status_code == 422


# ---------------- admin ----------------
def test_admin_wallet_routes_are_admin_only(client, auth_headers):
    for path in ("/api/admin/wallet/summary", "/api/admin/wallet/requests", "/api/admin/wallet/users"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth_headers).status_code == 403


def test_admin_summary_and_adjust(client, auth_headers):
    admin = make_admin(client)
    uid = user_id(client, auth_headers)
    assert client.post(f"/api/admin/wallet/users/{uid}/adjust", json={"amount": "250", "note": "goodwill"}, headers=admin).status_code == 200
    assert client.post(f"/api/admin/wallet/users/{uid}/adjust", json={"amount": "-1000", "note": "too much"}, headers=admin).status_code == 409
    s = client.get("/api/admin/wallet/summary", headers=admin).json()
    assert s["in_wallets"] == "250.00" and s["pending"]["deposit"] == 0
    users = client.get("/api/admin/wallet/users", headers=admin).json()["items"]
    assert any(u["id"] == uid and u["balance"] == "250.00" for u in users)
    tx = client.get(f"/api/admin/wallet/users/{uid}/transactions", headers=admin).json()
    assert tx["total"] == 1 and tx["items"][0]["kind"] == "adjustment"
