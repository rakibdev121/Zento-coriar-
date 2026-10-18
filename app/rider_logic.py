"""Shared rider helpers: commission maths, Bangladesh-time days and image validation."""
import base64
import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

BD_TZ = timezone(timedelta(hours=6))  # Bangladesh Standard Time, no DST
TERMINAL = ("delivered", "cancelled")
MAX_IMAGE_BYTES = 1_500_000
MAX_DATA_URL_CHARS = 2_100_000  # 1.5 MB as base64 plus the "data:image/...;base64," prefix

_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=\s]+)$")


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_day(dt: datetime) -> date:
    return aware(dt).astimezone(BD_TZ).date()


def commission_for(price_total) -> Decimal:
    """Rider commission for a parcel: price_total x RIDER_COMMISSION_RATE (default 20%), rounded to 2 places."""
    from app.config import get_settings  # imported lazily so this module stays importable without settings

    return (Decimal(price_total) * get_settings().rider_commission_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def settle_delivery(parcel, now: datetime | None = None) -> None:
    """Call when a parcel becomes delivered: stamp the time and lock in the rider's commission (once)."""
    parcel.delivered_at = parcel.delivered_at or now or datetime.now(timezone.utc)
    # A rider who was offered the parcel but never accepted it earns nothing.
    if parcel.rider_id and parcel.rider_response != "pending" and parcel.rider_commission is None:
        parcel.rider_commission = commission_for(parcel.price_total)


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def parse_image_data_url(value: str) -> tuple[str, bytes]:
    """Validate a data:image/...;base64 URL and return (content_type, bytes). Raises ValueError with a user-facing message."""
    m = _DATA_URL.match((value or "").strip())
    if not m:
        raise ValueError("Upload a JPG, PNG or WebP image.")
    try:
        data = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
    except ValueError:
        raise ValueError("That image could not be read. Try another file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("That image is too large (1.5 MB maximum).")
    real = _sniff(data)
    if real is None or real != m.group(1):
        raise ValueError("That file is not a valid JPG, PNG or WebP image.")
    return real, data
