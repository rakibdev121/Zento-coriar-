from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import wallet
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import Parcel, TrackingEvent
from app.pdf import build_parcel_pdf
from app.routers.pricing import quote_for
from app.schemas import ParcelCreate, ParcelDetail, ParcelPage, ParcelStatus
from app.tracking import generate_tracking_number

router = APIRouter(prefix="/parcels", tags=["parcels"])


def _get_owned(db, user_id: int, parcel_id: int) -> Parcel:
    parcel = db.scalar(select(Parcel).where(Parcel.id == parcel_id, Parcel.user_id == user_id))
    if parcel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Parcel not found.")
    return parcel


def create_parcel_record(db, user_id: int, payload: ParcelCreate) -> Parcel:
    """Price server-side, take the price from the customer's wallet, store the parcel and its first tracking event.

    Shared with the admin panel. Money and parcel are saved in one transaction: no wallet balance, no parcel.
    """
    q = quote_for(payload)
    wallet.ensure_funds(wallet.lock_user(db, user_id), q.total)  # fail fast with a clear message
    breakdown = [{"code": l.code, "label": l.label, "amount": str(l.amount)} for l in q.lines]
    fields = payload.model_dump(exclude={"zone", "service"})
    for _ in range(5):  # retry on the (very unlikely) tracking-number collision
        parcel = Parcel(
            user_id=user_id, tracking_number=generate_tracking_number(), zone=payload.zone, service=payload.service,
            chargeable_weight_kg=q.chargeable_weight_kg, price_total=q.total, price_breakdown=breakdown, **fields,
        )
        parcel.events.append(TrackingEvent(status="booked", note="Booking confirmed. Waiting for pickup.", location=payload.pickup_city))
        db.add(parcel)
        try:
            db.flush()
            wallet.charge_booking(db, wallet.lock_user(db, user_id), parcel)
            db.commit()
            db.refresh(parcel)
            return parcel
        except IntegrityError:
            db.rollback()
    db.rollback()
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not create the booking. Please try again.")


@router.post("", response_model=ParcelDetail, status_code=status.HTTP_201_CREATED)
def create_parcel(payload: ParcelCreate, db: DbSession, user: CurrentUser):
    # Price is always recomputed server-side; the client's quote is only a preview.
    return create_parcel_record(db, user.id, payload)


@router.get("", response_model=ParcelPage)
def list_parcels(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
    status_filter: Annotated[ParcelStatus | None, Query(alias="status")] = None,
):
    conditions = [Parcel.user_id == user.id]
    if status_filter:
        conditions.append(Parcel.status == status_filter)
    total = db.scalar(select(func.count()).select_from(Parcel).where(*conditions)) or 0
    items = db.scalars(
        select(Parcel).where(*conditions).order_by(Parcel.created_at.desc(), Parcel.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ParcelPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{parcel_id}", response_model=ParcelDetail)
def get_parcel(parcel_id: int, db: DbSession, user: CurrentUser):
    return _get_owned(db, user.id, parcel_id)


@router.get("/{parcel_id}/pdf")
def parcel_pdf(parcel_id: int, db: DbSession, user: CurrentUser):
    p = _get_owned(db, user.id, parcel_id)
    return Response(content=build_parcel_pdf(p, get_settings().currency, audience="customer"), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{p.tracking_number}.pdf"', "Cache-Control": "no-store"})


@router.post("/{parcel_id}/cancel", response_model=ParcelDetail)
def cancel_parcel(parcel_id: int, db: DbSession, user: CurrentUser):
    parcel = _get_owned(db, user.id, parcel_id)
    if parcel.status != "booked":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only parcels that have not been picked up can be cancelled.")
    parcel.status = "cancelled"
    parcel.events.append(TrackingEvent(status="cancelled", note="Cancelled by the customer.", location=None))
    wallet.refund_booking(db, parcel)
    db.commit()
    db.refresh(parcel)
    return parcel
