"""Admin panel API. Every route requires an authenticated user with is_admin = true."""
import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError

from app import pricing as pricing_rules
from app.config import get_settings
from app.deps import CurrentAdmin, DbSession
from app.models import ActivityLog, CourierProvider, Parcel, Rider, ServiceArea, TrackingEvent, User
from app.routers.parcels import create_parcel_record
from app.schemas import City, Name, ParcelCreate, ParcelStatus, Phone, RegisterRequest, _check_phone
from app.security import hash_password, verify_password

router = APIRouter(prefix="/admin", tags=["admin"])

LOCAL_TZ = timezone(timedelta(hours=6))  # Bangladesh Standard Time, no DST
ACTIVE_STATUSES = ("picked_up", "in_transit", "out_for_delivery")
FLOW = ["booked", "picked_up", "in_transit", "out_for_delivery", "delivered"]
DEFAULT_NOTES = {
    "picked_up": "Parcel picked up from the sender.", "in_transit": "Parcel is in transit.",
    "out_for_delivery": "Parcel is out for delivery.", "delivered": "Parcel delivered.", "cancelled": "Cancelled by ZENTO COURIER.",
}


# ---------------- helpers ----------------
def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local_day(dt: datetime) -> date:
    return _aware(dt).astimezone(LOCAL_TZ).date()


def _iso(dt: datetime | None) -> str | None:
    return _aware(dt).astimezone(timezone.utc).isoformat() if dt else None


def _trend(current: int, previous: int) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return round((current - previous) / previous * 100, 1)


def _eta(p: Parcel) -> str | None:
    if p.status == "cancelled":
        return None
    if p.status == "delivered":
        return _local_day(p.updated_at).isoformat()
    days = pricing_rules.ETA_DAYS.get((p.zone, p.service), (1, 3))[1]
    return (_local_day(p.created_at) + timedelta(days=days)).isoformat()


def _log(db, kind: str, title: str, detail: str | None = None) -> None:
    db.add(ActivityLog(kind=kind, title=title, detail=detail))


def _parcel_row(p: Parcel) -> dict:
    return {
        "id": p.id, "tracking_number": p.tracking_number, "status": p.status, "zone": p.zone, "service": p.service,
        "customer_name": p.user.full_name, "customer_email": p.user.email, "sender_name": p.sender_name,
        "recipient_name": p.recipient_name, "pickup_city": p.pickup_city, "delivery_city": p.delivery_city,
        "price_total": str(p.price_total), "rider": {"id": p.rider.id, "name": p.rider.full_name} if p.rider else None,
        "provider": {"id": p.provider.id, "name": p.provider.name} if p.provider else None,
        "eta": _eta(p), "created_at": _iso(p.created_at),
    }


def _parcel_detail(p: Parcel) -> dict:
    return {
        **_parcel_row(p), "sender_phone": p.sender_phone, "pickup_address": p.pickup_address, "recipient_phone": p.recipient_phone,
        "delivery_address": p.delivery_address, "weight_kg": str(p.weight_kg), "chargeable_weight_kg": str(p.chargeable_weight_kg),
        "declared_value": str(p.declared_value), "fragile": p.fragile, "description": p.description,
        "price_breakdown": p.price_breakdown, "customer_phone": p.user.phone,
        "events": [{"status": e.status, "note": e.note, "location": e.location, "created_at": _iso(e.created_at)} for e in p.events],
    }


def _parcel_filters(q: str | None, status_filter: str | None):
    conds = []
    if status_filter == "active":
        conds.append(Parcel.status.in_(ACTIVE_STATUSES))
    elif status_filter:
        conds.append(Parcel.status == status_filter)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        conds.append(or_(
            func.lower(Parcel.tracking_number).like(like), func.lower(Parcel.recipient_name).like(like),
            func.lower(Parcel.sender_name).like(like), func.lower(Parcel.pickup_city).like(like),
            func.lower(Parcel.delivery_city).like(like),
            Parcel.user_id.in_(select(User.id).where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))),
        ))
    return conds


def _feed(db, limit: int) -> list[dict]:
    items = []
    for p in db.scalars(select(Parcel).order_by(Parcel.created_at.desc()).limit(limit)):
        items.append({"kind": "booking", "title": "New Booking", "detail": p.tracking_number, "created_at": _iso(p.created_at)})
    for u in db.scalars(select(User).where(User.is_admin.is_(False)).order_by(User.created_at.desc()).limit(limit)):
        items.append({"kind": "customer", "title": "Customer Registered", "detail": u.full_name, "created_at": _iso(u.created_at)})
    for a in db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(limit)):
        items.append({"kind": a.kind, "title": a.title, "detail": a.detail, "created_at": _iso(a.created_at)})
    items.sort(key=lambda i: datetime.fromisoformat(i["created_at"]), reverse=True)
    return items[:limit]


def _commit_or_409(db, message: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, message)


def _get_or_404(db, model, obj_id: int, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found.")
    return obj


# ---------------- dashboard ----------------
@router.get("/dashboard")
def dashboard(db: DbSession, admin: CurrentAdmin):
    now = datetime.now(timezone.utc)
    w1, w2 = now - timedelta(days=7), now - timedelta(days=14)

    def count_between(model, start, end, *conds):
        return db.scalar(select(func.count()).select_from(model).where(model.created_at >= start, model.created_at < end, *conds)) or 0

    total = lambda model, *c: db.scalar(select(func.count()).select_from(model).where(*c)) or 0  # noqa: E731
    not_admin = User.is_admin.is_(False)
    stats = {
        "total_parcels": {"value": total(Parcel), "trend": _trend(count_between(Parcel, w1, now), count_between(Parcel, w2, w1))},
        "total_bookings": {"value": total(Parcel, Parcel.status != "cancelled"),
                           "trend": _trend(count_between(Parcel, w1, now, Parcel.status != "cancelled"), count_between(Parcel, w2, w1, Parcel.status != "cancelled"))},
        "active_customers": {"value": total(User, not_admin, User.is_active.is_(True)),
                             "trend": _trend(count_between(User, w1, now, not_admin), count_between(User, w2, w1, not_admin))},
        "active_riders": {"value": total(Rider, Rider.is_active.is_(True)),
                          "trend": _trend(count_between(Rider, w1, now), count_between(Rider, w2, w1))},
    }

    today = now.astimezone(LOCAL_TZ).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    buckets = {d: {"delivered": 0, "in_transit": 0, "pending": 0} for d in days}
    since = now - timedelta(days=8)
    for created, st in db.execute(select(Parcel.created_at, Parcel.status).where(Parcel.created_at >= since)):
        d = _local_day(created)
        if d in buckets and st != "cancelled":
            buckets[d]["delivered" if st == "delivered" else "pending" if st == "booked" else "in_transit"] += 1
    chart = [{"date": d.isoformat(), **buckets[d]} for d in days]

    live = db.scalar(select(Parcel).where(Parcel.status.in_(ACTIVE_STATUSES)).order_by(Parcel.updated_at.desc(), Parcel.id.desc()).limit(1))
    live_out = None
    if live:
        live_out = {"tracking_number": live.tracking_number, "status": live.status, "pickup_city": live.pickup_city,
                    "delivery_city": live.delivery_city, "rider": live.rider.full_name if live.rider else None,
                    "note": live.events[-1].note if live.events else None}

    recent = db.scalars(select(Parcel).order_by(Parcel.created_at.desc(), Parcel.id.desc()).limit(5)).all()

    rows = db.execute(
        select(CourierProvider.name, func.count(Parcel.id)).join(Parcel, Parcel.provider_id == CourierProvider.id)
        .group_by(CourierProvider.id, CourierProvider.name).order_by(func.count(Parcel.id).desc())
    ).all()
    assigned = sum(c for _, c in rows)
    providers = [{"name": n, "share": round(c / assigned * 100)} for n, c in rows[:3]] if assigned else []
    if assigned and len(rows) > 3:
        providers.append({"name": "Others", "share": max(0, 100 - sum(p["share"] for p in providers))})

    return {
        "currency": get_settings().currency, "stats": stats, "chart": chart, "live": live_out,
        "recent_parcels": [_parcel_row(p) for p in recent], "providers": providers, "activities": _feed(db, 5),
        "pending_bookings": total(Parcel, Parcel.status == "booked"),
    }


# ---------------- parcels & bookings ----------------
@router.get("/parcels")
def list_parcels(
    db: DbSession, admin: CurrentAdmin, q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    status_filter: Annotated[str | None, Query(alias="status", pattern="^(booked|picked_up|in_transit|out_for_delivery|delivered|cancelled|active)$")] = None,
):
    conds = _parcel_filters(q, status_filter)
    total = db.scalar(select(func.count()).select_from(Parcel).where(*conds)) or 0
    items = db.scalars(select(Parcel).where(*conds).order_by(Parcel.created_at.desc(), Parcel.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_parcel_row(p) for p in items], "total": total, "page": page, "page_size": page_size}


def _csv_cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s  # block spreadsheet formula injection


@router.get("/parcels/export.csv")
def export_parcels(db: DbSession, admin: CurrentAdmin, q: str | None = None,
                   status_filter: Annotated[str | None, Query(alias="status", pattern="^(booked|picked_up|in_transit|out_for_delivery|delivered|cancelled|active)$")] = None):
    parcels = db.scalars(select(Parcel).where(*_parcel_filters(q, status_filter)).order_by(Parcel.created_at.desc()).limit(10000)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Tracking", "Status", "Customer", "Sender", "Recipient", "From", "To", "Zone", "Service", "Rider", "Provider", "Price", "Created"])
    for p in parcels:
        r = _parcel_row(p)
        w.writerow([_csv_cell(x) for x in (r["tracking_number"], r["status"], r["customer_name"], r["sender_name"], r["recipient_name"],
                                           r["pickup_city"], r["delivery_city"], r["zone"], r["service"], r["rider"]["name"] if r["rider"] else "",
                                           r["provider"]["name"] if r["provider"] else "", r["price_total"], r["created_at"])])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="zento-parcels.csv"'})


@router.get("/parcels/{parcel_id}")
def parcel_detail(parcel_id: int, db: DbSession, admin: CurrentAdmin):
    return _parcel_detail(_get_or_404(db, Parcel, parcel_id, "Parcel"))


class ParcelUpdate(BaseModel):
    status: ParcelStatus | None = None
    note: Annotated[str, Field(max_length=255)] | None = None
    location: Annotated[str, Field(max_length=80)] | None = None
    rider_id: int | None = None
    provider_id: int | None = None


@router.patch("/parcels/{parcel_id}")
def update_parcel(parcel_id: int, payload: ParcelUpdate, db: DbSession, admin: CurrentAdmin):
    p = _get_or_404(db, Parcel, parcel_id, "Parcel")
    sent = payload.model_fields_set
    terminal = p.status in ("delivered", "cancelled")

    if "rider_id" in sent and payload.rider_id != p.rider_id:
        if terminal:
            raise HTTPException(status.HTTP_409_CONFLICT, "This parcel is already closed.")
        if payload.rider_id is None:
            p.rider_id = None
        else:
            rider = _get_or_404(db, Rider, payload.rider_id, "Rider")
            if not rider.is_active:
                raise HTTPException(status.HTTP_409_CONFLICT, "That rider is inactive.")
            p.rider_id = rider.id
            _log(db, "rider", "Rider Assigned", f"{rider.full_name} · {p.tracking_number}")
    if "provider_id" in sent and payload.provider_id != p.provider_id:
        if terminal:
            raise HTTPException(status.HTTP_409_CONFLICT, "This parcel is already closed.")
        p.provider_id = None if payload.provider_id is None else _get_or_404(db, CourierProvider, payload.provider_id, "Courier provider").id

    if payload.status and payload.status != p.status:
        new = payload.status
        if new == "cancelled":
            if terminal:
                raise HTTPException(status.HTTP_409_CONFLICT, "This parcel is already closed.")
        elif terminal or FLOW.index(new) <= FLOW.index(p.status):
            raise HTTPException(status.HTTP_409_CONFLICT, f"A {p.status.replace('_', ' ')} parcel cannot move to {new.replace('_', ' ')}.")
        p.status = new
        p.events.append(TrackingEvent(status=new, note=(payload.note or "").strip() or DEFAULT_NOTES[new], location=(payload.location or "").strip() or None))
        _log(db, "delivered" if new == "delivered" else "status", "Parcel Delivered" if new == "delivered" else "Status Updated",
             p.tracking_number if new == "delivered" else f"{p.tracking_number} · {new.replace('_', ' ')}")
    db.commit()
    db.refresh(p)
    return _parcel_detail(p)


class BookingCreate(ParcelCreate):
    user_id: int


@router.post("/bookings", status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: DbSession, admin: CurrentAdmin):
    customer = _get_or_404(db, User, payload.user_id, "Customer")
    parcel = create_parcel_record(db, customer.id, ParcelCreate(**payload.model_dump(exclude={"user_id"})))
    return _parcel_detail(parcel)


# ---------------- customers ----------------
def _customer_row(u: User, parcels: int, spent) -> dict:
    return {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone, "is_active": u.is_active,
            "parcels": parcels, "total_spent": str(Decimal(spent or 0)), "created_at": _iso(u.created_at)}


@router.get("/customers")
def list_customers(db: DbSession, admin: CurrentAdmin, q: str | None = None,
                   page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 10):
    conds = [User.is_admin.is_(False)]
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        conds.append(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like), User.phone.like(like)))
    total = db.scalar(select(func.count()).select_from(User).where(*conds)) or 0
    spent = func.coalesce(func.sum(case((Parcel.status != "cancelled", Parcel.price_total), else_=0)), 0)
    rows = db.execute(
        select(User, func.count(Parcel.id), spent).outerjoin(Parcel, Parcel.user_id == User.id).where(*conds)
        .group_by(User.id).order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [_customer_row(u, c, s) for u, c, s in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/customers", status_code=status.HTTP_201_CREATED)
def add_customer(payload: RegisterRequest, db: DbSession, admin: CurrentAdmin):
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    u = User(full_name=payload.full_name, email=payload.email, phone=payload.phone, password_hash=hash_password(payload.password))
    db.add(u)
    _commit_or_409(db, "An account with this email already exists.")
    db.refresh(u)
    return _customer_row(u, 0, 0)


class CustomerPatch(BaseModel):
    is_active: bool | None = None
    full_name: Name | None = None
    phone: Phone | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return v if v is None else _check_phone(v)


@router.patch("/customers/{user_id}")
def patch_customer(user_id: int, payload: CustomerPatch, db: DbSession, admin: CurrentAdmin):
    u = _get_or_404(db, User, user_id, "Customer")
    if u.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin accounts cannot be edited here.")
    for field in payload.model_fields_set:
        if getattr(payload, field) is not None:
            setattr(u, field, getattr(payload, field))
    db.commit()
    return _customer_row(u, db.scalar(select(func.count()).select_from(Parcel).where(Parcel.user_id == u.id)) or 0, 0)


# ---------------- riders ----------------
class RiderIn(BaseModel):
    full_name: Name
    phone: Phone
    vehicle: Literal["bike", "bicycle", "scooter", "van", "truck"] = "bike"
    city: City | None = None
    is_active: bool = True

    _p = field_validator("phone")(_check_phone)

    @field_validator("city", mode="before")
    @classmethod
    def _blank(cls, v):
        return v or None


def _rider_out(r: Rider, active: int = 0, delivered: int = 0) -> dict:
    return {"id": r.id, "full_name": r.full_name, "phone": r.phone, "vehicle": r.vehicle, "city": r.city, "is_active": r.is_active,
            "active_deliveries": active, "delivered": delivered, "created_at": _iso(r.created_at)}


@router.get("/riders")
def list_riders(db: DbSession, admin: CurrentAdmin):
    counts = defaultdict(lambda: [0, 0])
    for rid, st, n in db.execute(select(Parcel.rider_id, Parcel.status, func.count()).where(Parcel.rider_id.is_not(None)).group_by(Parcel.rider_id, Parcel.status)):
        if st in ACTIVE_STATUSES or st == "booked":
            counts[rid][0] += n
        elif st == "delivered":
            counts[rid][1] += n
    return {"items": [_rider_out(r, *counts[r.id]) for r in db.scalars(select(Rider).order_by(Rider.is_active.desc(), Rider.full_name))]}


@router.post("/riders", status_code=status.HTTP_201_CREATED)
def add_rider(payload: RiderIn, db: DbSession, admin: CurrentAdmin):
    r = Rider(**payload.model_dump())
    db.add(r)
    db.commit()
    return _rider_out(r)


@router.put("/riders/{rider_id}")
def edit_rider(rider_id: int, payload: RiderIn, db: DbSession, admin: CurrentAdmin):
    r = _get_or_404(db, Rider, rider_id, "Rider")
    for k, v in payload.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return _rider_out(r)


@router.delete("/riders/{rider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rider(rider_id: int, db: DbSession, admin: CurrentAdmin):
    db.delete(_get_or_404(db, Rider, rider_id, "Rider"))
    db.commit()


# ---------------- courier providers ----------------
class ProviderIn(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=80)]
    phone: Phone | None = None
    website: Annotated[str, Field(max_length=200)] | None = None
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, v):
        return v.strip()

    @field_validator("phone", "website", mode="before")
    @classmethod
    def _blank(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return v if v is None else _check_phone(v)

    @field_validator("website")
    @classmethod
    def _site(cls, v):
        if v is not None and not re.match(r"^https?://[^\s]+$", v):
            raise ValueError("Website must start with http:// or https://")
        return v


def _provider_out(p: CourierProvider, parcels: int = 0) -> dict:
    return {"id": p.id, "name": p.name, "phone": p.phone, "website": p.website, "is_active": p.is_active, "parcels": parcels, "created_at": _iso(p.created_at)}


@router.get("/providers")
def list_providers(db: DbSession, admin: CurrentAdmin):
    counts = dict(db.execute(select(Parcel.provider_id, func.count()).where(Parcel.provider_id.is_not(None)).group_by(Parcel.provider_id)).all())
    return {"items": [_provider_out(p, counts.get(p.id, 0)) for p in db.scalars(select(CourierProvider).order_by(CourierProvider.is_active.desc(), CourierProvider.name))]}


@router.post("/providers", status_code=status.HTTP_201_CREATED)
def add_provider(payload: ProviderIn, db: DbSession, admin: CurrentAdmin):
    p = CourierProvider(**payload.model_dump())
    db.add(p)
    _commit_or_409(db, "A provider with this name already exists.")
    return _provider_out(p)


@router.put("/providers/{provider_id}")
def edit_provider(provider_id: int, payload: ProviderIn, db: DbSession, admin: CurrentAdmin):
    p = _get_or_404(db, CourierProvider, provider_id, "Courier provider")
    for k, v in payload.model_dump().items():
        setattr(p, k, v)
    _commit_or_409(db, "A provider with this name already exists.")
    return _provider_out(p)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: int, db: DbSession, admin: CurrentAdmin):
    db.delete(_get_or_404(db, CourierProvider, provider_id, "Courier provider"))
    db.commit()


# ---------------- service areas ----------------
class AreaIn(BaseModel):
    city: City
    region: Annotated[str, Field(max_length=80)] | None = None
    is_active: bool = True

    @field_validator("city")
    @classmethod
    def _strip(cls, v):
        return v.strip()

    @field_validator("region", mode="before")
    @classmethod
    def _blank(cls, v):
        return (v.strip() or None) if isinstance(v, str) else v


def _area_out(a: ServiceArea, parcels: int = 0) -> dict:
    return {"id": a.id, "city": a.city, "region": a.region, "is_active": a.is_active, "parcels": parcels}


@router.get("/areas")
def list_areas(db: DbSession, admin: CurrentAdmin):
    counts = dict(db.execute(select(func.lower(Parcel.delivery_city), func.count()).group_by(func.lower(Parcel.delivery_city))).all())
    return {"items": [_area_out(a, counts.get(a.city.lower(), 0)) for a in db.scalars(select(ServiceArea).order_by(ServiceArea.is_active.desc(), ServiceArea.city))]}


@router.post("/areas", status_code=status.HTTP_201_CREATED)
def add_area(payload: AreaIn, db: DbSession, admin: CurrentAdmin):
    a = ServiceArea(**payload.model_dump())
    db.add(a)
    _commit_or_409(db, "This city is already listed.")
    return _area_out(a)


@router.put("/areas/{area_id}")
def edit_area(area_id: int, payload: AreaIn, db: DbSession, admin: CurrentAdmin):
    a = _get_or_404(db, ServiceArea, area_id, "Service area")
    for k, v in payload.model_dump().items():
        setattr(a, k, v)
    _commit_or_409(db, "This city is already listed.")
    return _area_out(a)


@router.delete("/areas/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_area(area_id: int, db: DbSession, admin: CurrentAdmin):
    db.delete(_get_or_404(db, ServiceArea, area_id, "Service area"))
    db.commit()


# ---------------- pricing (read-only: rates live in app/pricing.py) ----------------
@router.get("/pricing")
def pricing_overview(admin: CurrentAdmin):
    pr = pricing_rules
    return {
        "currency": get_settings().currency, "included_kg": str(pr.INCLUDED_KG), "volumetric_divisor": str(pr.VOLUMETRIC_DIVISOR),
        "zones": [{"id": k, "label": v["label"], "description": v["description"], "base": str(v["base"]), "per_kg": str(v["per_kg"])} for k, v in pr.ZONES.items()],
        "services": [{"id": k, "label": v["label"], "description": v["description"], "multiplier": str(v["multiplier"])} for k, v in pr.SERVICES.items()],
        "fees": {"fragile": str(pr.FRAGILE_FEE), "insurance_rate": str(pr.INSURANCE_RATE), "insurance_min": str(pr.INSURANCE_MIN)},
        "limits": {"max_weight_kg": str(pr.MAX_WEIGHT_KG), "max_dimension_cm": pr.MAX_DIMENSION_CM, "max_declared_value": str(pr.MAX_DECLARED_VALUE)},
        "eta": [{"zone": z, "service": s, "min_days": a, "max_days": b} for (z, s), (a, b) in pr.ETA_DAYS.items()],
    }


# ---------------- reports ----------------
@router.get("/reports")
def reports(db: DbSession, admin: CurrentAdmin, days: Annotated[int, Query(ge=1, le=365)] = 30):
    now = datetime.now(timezone.utc)
    today = now.astimezone(LOCAL_TZ).date()
    span = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    daily = {d: {"parcels": 0, "delivered": 0, "revenue": Decimal("0")} for d in span}
    by_status, by_zone, by_service = defaultdict(int), defaultdict(lambda: [0, Decimal("0")]), defaultdict(lambda: [0, Decimal("0")])
    total_rev, total = Decimal("0"), 0
    for created, st, zone, service, price in db.execute(
        select(Parcel.created_at, Parcel.status, Parcel.zone, Parcel.service, Parcel.price_total).where(Parcel.created_at >= now - timedelta(days=days + 1))
    ):
        d = _local_day(created)
        if d not in daily:
            continue
        total += 1
        by_status[st] += 1
        daily[d]["parcels"] += 1
        if st == "delivered":
            daily[d]["delivered"] += 1
        if st != "cancelled":
            daily[d]["revenue"] += price
            total_rev += price
            by_zone[zone][0] += 1; by_zone[zone][1] += price
            by_service[service][0] += 1; by_service[service][1] += price
    delivered = by_status.get("delivered", 0)
    return {
        "days": days, "currency": get_settings().currency,
        "totals": {"parcels": total, "revenue": str(total_rev), "delivered": delivered, "cancelled": by_status.get("cancelled", 0),
                   "delivery_rate": round(delivered / total * 100, 1) if total else 0},
        "daily": [{"date": d.isoformat(), "parcels": v["parcels"], "delivered": v["delivered"], "revenue": str(v["revenue"])} for d, v in daily.items()],
        "by_status": dict(by_status),
        "by_zone": [{"name": k, "parcels": v[0], "revenue": str(v[1])} for k, v in by_zone.items()],
        "by_service": [{"name": k, "parcels": v[0], "revenue": str(v[1])} for k, v in by_service.items()],
    }


# ---------------- notifications & account ----------------
@router.get("/notifications")
def notifications(db: DbSession, admin: CurrentAdmin):
    return {"items": _feed(db, 30)}


class PasswordChange(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v):
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number.")
        return v


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: PasswordChange, db: DbSession, admin: CurrentAdmin):
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    admin.password_hash = hash_password(payload.new_password)
    db.commit()
