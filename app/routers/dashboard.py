from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import Parcel
from app.schemas import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: DbSession, user: CurrentUser):
    counts = dict(db.execute(select(Parcel.status, func.count()).where(Parcel.user_id == user.id).group_by(Parcel.status)).all())
    spent = db.scalar(select(func.coalesce(func.sum(Parcel.price_total), 0)).where(Parcel.user_id == user.id, Parcel.status != "cancelled"))
    recent = db.scalars(select(Parcel).where(Parcel.user_id == user.id).order_by(Parcel.created_at.desc(), Parcel.id.desc()).limit(5)).all()
    in_progress = sum(counts.get(s, 0) for s in ("booked", "picked_up", "in_transit", "out_for_delivery"))
    return DashboardSummary(
        total_parcels=sum(counts.values()), in_progress=in_progress, delivered=counts.get("delivered", 0),
        cancelled=counts.get("cancelled", 0), total_spent=Decimal(spent or 0), currency=get_settings().currency, recent=recent,
    )
