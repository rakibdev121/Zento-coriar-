from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DbSession
from app.models import Parcel
from app.schemas import PublicTracking
from app.tracking import is_valid_tracking_number, normalise_tracking_number

router = APIRouter(prefix="/track", tags=["tracking"])


@router.get("/{tracking_number}", response_model=PublicTracking)
def track(tracking_number: str, db: DbSession):
    number = normalise_tracking_number(tracking_number)
    if not is_valid_tracking_number(number):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tracking numbers look like ZNT followed by 9 letters and digits.")
    parcel = db.scalar(select(Parcel).where(Parcel.tracking_number == number))
    if parcel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "We could not find a shipment with that tracking number.")
    return parcel
