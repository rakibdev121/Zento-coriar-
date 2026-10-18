"""Pydantic request/response schemas."""
import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

from app.pricing import MAX_DECLARED_VALUE, MAX_DIMENSION_CM, MAX_WEIGHT_KG

Zone = Literal["local", "regional", "national"]
Service = Literal["standard", "express", "same_day"]
ParcelStatus = Literal["booked", "picked_up", "in_transit", "out_for_delivery", "delivered", "cancelled"]

_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{6,19}$")


def _text(min_length: int, max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


Name = _text(2, 100)
Address = _text(5, 255)
City = _text(2, 80)
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]


def _check_phone(v: str) -> str:
    if not _PHONE_RE.match(v):
        raise ValueError("Enter a valid phone number, for example 01712345678.")
    return v


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    full_name: Name
    email: EmailStr
    phone: Phone
    password: Annotated[str, Field(min_length=8, max_length=128)]

    _phone = field_validator("phone")(_check_phone)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    phone: str
    is_admin: bool = False
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Pricing ----------
class QuoteRequest(BaseModel):
    zone: Zone
    service: Service
    weight_kg: Annotated[Decimal, Field(gt=0, le=MAX_WEIGHT_KG, max_digits=6, decimal_places=2)]
    length_cm: int | None = Field(default=None, ge=1, le=MAX_DIMENSION_CM)
    width_cm: int | None = Field(default=None, ge=1, le=MAX_DIMENSION_CM)
    height_cm: int | None = Field(default=None, ge=1, le=MAX_DIMENSION_CM)
    declared_value: Annotated[Decimal, Field(ge=0, le=MAX_DECLARED_VALUE, max_digits=10, decimal_places=2)] = Decimal("0")
    fragile: bool = False

    @model_validator(mode="after")
    def _cross_checks(self):
        dims = (self.length_cm, self.width_cm, self.height_cm)
        if any(d is not None for d in dims) and any(d is None for d in dims):
            raise ValueError("Provide length, width and height together, or leave all three empty.")
        if self.service == "same_day" and self.zone != "local":
            raise ValueError("Same-day delivery is only available in the local zone.")
        return self


class PriceLineOut(BaseModel):
    code: str
    label: str
    amount: Decimal


class QuoteOut(BaseModel):
    currency: str
    chargeable_weight_kg: Decimal
    lines: list[PriceLineOut]
    total: Decimal
    eta_min_days: int
    eta_max_days: int


# ---------- Parcels ----------
class ParcelCreate(QuoteRequest):
    sender_name: Name
    sender_phone: Phone
    pickup_address: Address
    pickup_city: City
    recipient_name: Name
    recipient_phone: Phone
    delivery_address: Address
    delivery_city: City
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    # Cash on Delivery: the rider collects this from the recipient; after delivery it is credited to the sender's wallet.
    cod_amount: Annotated[Decimal, Field(ge=0, le=500_000, max_digits=10, decimal_places=2)] = Decimal("0")

    _sp = field_validator("sender_phone")(_check_phone)
    _rp = field_validator("recipient_phone")(_check_phone)

    @field_validator("description")
    @classmethod
    def _blank_to_none(cls, v):
        return v or None


class TrackingEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: ParcelStatus
    note: str
    location: str | None
    created_at: datetime


class ParcelSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tracking_number: str
    status: ParcelStatus
    zone: Zone
    service: Service
    recipient_name: str
    pickup_city: str
    delivery_city: str
    price_total: Decimal
    cod_amount: Decimal = Decimal("0")
    created_at: datetime


class ParcelDetail(ParcelSummary):
    sender_name: str
    sender_phone: str
    pickup_address: str
    recipient_phone: str
    delivery_address: str
    weight_kg: Decimal
    chargeable_weight_kg: Decimal
    length_cm: int | None
    width_cm: int | None
    height_cm: int | None
    declared_value: Decimal
    fragile: bool
    description: str | None
    price_breakdown: list[PriceLineOut]
    events: list[TrackingEventOut]


class ParcelPage(BaseModel):
    items: list[ParcelSummary]
    total: int
    page: int
    page_size: int


class PublicTracking(BaseModel):
    """Public view: cities and status only, no names, phones or street addresses."""
    model_config = ConfigDict(from_attributes=True)
    tracking_number: str
    status: ParcelStatus
    service: Service
    pickup_city: str
    delivery_city: str
    created_at: datetime
    events: list[TrackingEventOut]


class DashboardSummary(BaseModel):
    total_parcels: int
    in_progress: int
    delivered: int
    cancelled: int
    total_spent: Decimal
    currency: str
    recent: list[ParcelSummary]
