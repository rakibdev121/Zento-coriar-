"""Rider app API (/api/rider/*).

Riders apply here, then sign in with the normal /api/auth/login. An admin approves the application and assigns parcels;
the rider accepts or rejects each one, moves accepted parcels to picked up / out for delivery / delivered, and earns a
commission (RIDER_COMMISSION_RATE, default 20% of the parcel price) when a parcel is delivered.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import wallet
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import ActivityLog, Parcel, Rider, RiderDocument, TrackingEvent, User
from app.rider_logic import BD_TZ, MAX_DATA_URL_CHARS, TERMINAL, aware, commission_for, local_day, parse_image_data_url, settle_delivery
from app.schemas import City, RegisterRequest, UserOut
from app.security import create_access_token, hash_password

router = APIRouter(prefix="/rider", tags=["rider"])

Vehicle = Literal["bike", "bicycle", "scooter", "van", "truck"]
DataUrl = Annotated[str, Field(max_length=MAX_DATA_URL_CHARS)]


def _iso(dt: datetime | None) -> str | None:
    return aware(dt).astimezone(timezone.utc).isoformat() if dt else None


# ---------------- apply ----------------
class RiderApply(RegisterRequest):
    city: City
    vehicle: Vehicle = "bike"
    id_type: Literal["nid", "passport"]
    id_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=40)]
    photo: DataUrl
    id_document: DataUrl

    @field_validator("id_number")
    @classmethod
    def _id_number(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9 \-/]+$", v):
            raise ValueError("Use only letters, numbers, spaces and dashes.")
        return v

    @field_validator("photo", "id_document")
    @classmethod
    def _image(cls, v: str) -> str:
        parse_image_data_url(v)  # raises ValueError with a readable message
        return v


def _rider_me(r: Rider) -> dict:
    return {
        "id": r.id, "full_name": r.full_name, "email": r.user.email if r.user else None, "phone": r.phone, "vehicle": r.vehicle,
        "city": r.city, "status": r.status, "is_active": r.is_active, "reject_reason": r.reject_reason, "id_type": r.id_type,
        "id_number_masked": f"\u2022\u2022\u2022 {r.id_number[-3:]}" if r.id_number else None,
    }


@router.post("/apply", status_code=status.HTTP_201_CREATED)
def apply(payload: RiderApply, db: DbSession):
    conflict = HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists. Use a different email to apply as a rider.")
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise conflict
    user = User(full_name=payload.full_name, email=payload.email, phone=payload.phone, password_hash=hash_password(payload.password))
    rider = Rider(full_name=payload.full_name, phone=payload.phone, vehicle=payload.vehicle, city=payload.city, is_active=False,
                  status="pending", id_type=payload.id_type, id_number=payload.id_number, user=user)
    db.add(rider)
    try:
        db.flush()
    except IntegrityError:  # concurrent application with the same email
        db.rollback()
        raise conflict
    for kind, value in (("photo", payload.photo), ("id_document", payload.id_document)):
        content_type, data = parse_image_data_url(value)
        db.add(RiderDocument(rider_id=rider.id, kind=kind, content_type=content_type, data=data))
    db.add(ActivityLog(kind="rider", title="Rider Application", detail=rider.full_name))
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user.id), "token_type": "bearer",
            "user": UserOut.model_validate(user).model_dump(mode="json"), "rider": _rider_me(rider)}


# ---------------- who am I ----------------
def _current_rider(user: CurrentUser, db: DbSession) -> Rider:
    rider = db.scalar(select(Rider).where(Rider.user_id == user.id))
    if rider is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is not a rider account.")
    return rider


CurrentRider = Annotated[Rider, Depends(_current_rider)]


def _approved_rider(rider: CurrentRider) -> Rider:
    if rider.status == "pending":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your application is still being reviewed.")
    if rider.status == "rejected":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your application was not approved.")
    if not rider.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your rider account is switched off. Contact ZENTO COURIER.")
    return rider


ApprovedRider = Annotated[Rider, Depends(_approved_rider)]


@router.get("/me")
def me(rider: CurrentRider):
    return _rider_me(rider)


@router.get("/photo")
def my_photo(rider: CurrentRider, db: DbSession):
    doc = db.scalar(select(RiderDocument).where(RiderDocument.rider_id == rider.id, RiderDocument.kind == "photo"))
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo on file.")
    return Response(content=doc.data, media_type=doc.content_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


# ---------------- parcels ----------------
def _parcel_out(p: Parcel) -> dict:
    """What a rider sees. Names and phone numbers appear only after the rider has accepted the parcel."""
    out = {
        "id": p.id, "tracking_number": p.tracking_number, "status": p.status, "rider_response": p.rider_response, "service": p.service,
        "zone": p.zone, "weight_kg": str(p.weight_kg), "fragile": p.fragile, "description": p.description,
        "pickup_address": p.pickup_address, "pickup_city": p.pickup_city, "delivery_address": p.delivery_address, "delivery_city": p.delivery_city,
        "price_total": str(p.price_total), "cod_amount": str(p.cod_amount or 0),
        "commission": str(p.rider_commission if p.rider_commission is not None else commission_for(p.price_total)),
        "assigned_at": _iso(p.rider_assigned_at), "delivered_at": _iso(p.delivered_at), "created_at": _iso(p.created_at), "contact": None,
    }
    if p.rider_response == "accepted" or (p.rider_response is None and p.rider_id):
        out["contact"] = {"sender_name": p.sender_name, "sender_phone": p.sender_phone,
                          "recipient_name": p.recipient_name, "recipient_phone": p.recipient_phone}
    return out


def _own_parcel(db, rider: Rider, parcel_id: int) -> Parcel:
    p = db.scalar(select(Parcel).where(Parcel.id == parcel_id, Parcel.rider_id == rider.id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parcel not found.")
    return p


def _log(db, kind: str, title: str, detail: str) -> None:
    db.add(ActivityLog(kind=kind, title=title, detail=detail))


def _open_parcels(db, rider: Rider, response: str) -> list[Parcel]:
    return list(db.scalars(
        select(Parcel).where(Parcel.rider_id == rider.id, Parcel.rider_response == response, Parcel.status.not_in(TERMINAL))
        .order_by(Parcel.created_at, Parcel.id)))


@router.get("/parcels")
def list_parcels(rider: ApprovedRider, db: DbSession, tab: Annotated[Literal["requests", "active", "history"], Query()] = "active"):
    if tab == "requests":
        items = _open_parcels(db, rider, "pending")
    elif tab == "active":
        items = _open_parcels(db, rider, "accepted")
    else:
        items = list(db.scalars(select(Parcel).where(Parcel.rider_id == rider.id, Parcel.status.in_(TERMINAL))
                                .order_by(Parcel.updated_at.desc(), Parcel.id.desc()).limit(100)))
    return {"items": [_parcel_out(p) for p in items]}


class RespondIn(BaseModel):
    action: Literal["accept", "reject"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


@router.post("/parcels/{parcel_id}/respond")
def respond(parcel_id: int, payload: RespondIn, rider: ApprovedRider, db: DbSession):
    p = _own_parcel(db, rider, parcel_id)
    if p.rider_response != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already answered this parcel.")
    if p.status in TERMINAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "This parcel is already closed.")
    if payload.action == "accept":
        p.rider_response = "accepted"
        p.events.append(TrackingEvent(status=p.status, note="A rider has accepted your parcel.", location=p.pickup_city))
        _log(db, "rider", "Rider Accepted", f"{rider.full_name} · {p.tracking_number}")
    else:
        note = f"Rejected by {rider.full_name}" + (f": {payload.reason}" if payload.reason else "")
        p.rider_note = note[:255]
        p.rider_response, p.rider_id, p.rider_assigned_at = "rejected", None, None
        _log(db, "rider", "Rider Rejected", f"{rider.full_name} · {p.tracking_number}")
    db.commit()
    db.refresh(p)
    return _parcel_out(p)


# rider may only move an accepted parcel forward, one step at a time
NEXT_STEP = {"booked": ("picked_up",), "picked_up": ("out_for_delivery",), "in_transit": ("out_for_delivery",), "out_for_delivery": ("delivered",)}
STEP_NOTE = {"picked_up": "Rider picked up the parcel from the sender.", "out_for_delivery": "Parcel is out for delivery.", "delivered": "Parcel delivered."}


class StatusIn(BaseModel):
    status: Literal["picked_up", "out_for_delivery", "delivered"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None


@router.post("/parcels/{parcel_id}/status")
def update_status(parcel_id: int, payload: StatusIn, rider: ApprovedRider, db: DbSession):
    p = _own_parcel(db, rider, parcel_id)
    if p.rider_response == "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Accept the parcel first.")
    if p.status in TERMINAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "This parcel is already closed.")
    if payload.status not in NEXT_STEP.get(p.status, ()):
        want = NEXT_STEP.get(p.status, ("nothing",))[0].replace("_", " ")
        raise HTTPException(status.HTTP_409_CONFLICT, f"This parcel must be marked {want} next.")
    p.status = payload.status
    place = p.pickup_city if payload.status == "picked_up" else p.delivery_city
    p.events.append(TrackingEvent(status=payload.status, note=payload.note or STEP_NOTE[payload.status], location=place))
    if payload.status == "delivered":
        settle_delivery(p)
        wallet.settle_parcel_money(db, p)  # commission into the rider wallet, COD into the customer wallet
        _log(db, "delivered", "Parcel Delivered", p.tracking_number)
    else:
        _log(db, "status", "Status Updated", f"{p.tracking_number} · {payload.status.replace('_', ' ')}")
    db.commit()
    db.refresh(p)
    return _parcel_out(p)


# ---------------- earnings ----------------
def _earnings(db, rider: Rider) -> dict:
    rows = [(local_day(d or u), Decimal(c)) for d, u, c in db.execute(
        select(Parcel.delivered_at, Parcel.updated_at, Parcel.rider_commission)
        .where(Parcel.rider_id == rider.id, Parcel.status == "delivered", Parcel.rider_commission.is_not(None)))]
    today = datetime.now(timezone.utc).astimezone(BD_TZ).date()
    by_day: dict = defaultdict(Decimal)
    for day, amount in rows:
        by_day[day] += amount
    streak, day = 0, today if today in by_day else today - timedelta(days=1)
    while day in by_day:
        streak, day = streak + 1, day - timedelta(days=1)
    return {
        "today": sum((a for d, a in by_day.items() if d == today), Decimal(0)),
        "week": sum((a for d, a in by_day.items() if today - timedelta(days=6) <= d <= today), Decimal(0)),
        "month": sum((a for d, a in by_day.items() if (d.year, d.month) == (today.year, today.month)), Decimal(0)),
        "total": sum(by_day.values(), Decimal(0)), "streak": streak, "delivered": len(rows),
    }


def _rate_percent() -> int:
    return int((get_settings().rider_commission_rate * 100).to_integral_value())


def _wallet_out(db, user) -> dict:
    """Wallet balance, the COD cash still owed to ZENTO and what may be withdrawn now."""
    return {**wallet.snapshot(db, user), "pending_cod_deposit": str(wallet.pending_cod_deposits(db, user.id))}


@router.get("/dashboard")
def dashboard(rider: ApprovedRider, user: CurrentUser, db: DbSession):
    settings, e = get_settings(), _earnings(db, rider)
    goal = settings.rider_daily_goal
    active = _open_parcels(db, rider, "accepted")
    return {
        "currency": settings.currency, "rate_percent": _rate_percent(), "balance": str(e["total"]), "wallet": _wallet_out(db, user), "today": str(e["today"]), "goal": str(goal),
        "goal_percent": 0 if goal <= 0 else min(100, int(e["today"] / goal * 100)), "streak": e["streak"], "delivered_count": e["delivered"],
        "active": [_parcel_out(p) for p in active], "requests": [_parcel_out(p) for p in _open_parcels(db, rider, "pending")],
    }


@router.get("/earnings")
def earnings(rider: ApprovedRider, db: DbSession):
    e = _earnings(db, rider)
    items = db.scalars(select(Parcel).where(Parcel.rider_id == rider.id, Parcel.status == "delivered", Parcel.rider_commission.is_not(None))
                       .order_by(Parcel.updated_at.desc(), Parcel.id.desc()).limit(50))
    return {
        "currency": get_settings().currency, "rate_percent": _rate_percent(),
        **{k: str(e[k]) for k in ("today", "week", "month", "total")}, "delivered": e["delivered"], "streak": e["streak"],
        "items": [{"id": p.id, "tracking_number": p.tracking_number, "delivered_at": _iso(p.delivered_at or p.updated_at),
                   "price_total": str(p.price_total), "commission": str(p.rider_commission)} for p in items],
    }
