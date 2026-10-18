"""ORM models."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, false, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

PARCEL_STATUSES = ("booked", "picked_up", "in_transit", "out_for_delivery", "delivered", "cancelled")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parcels: Mapped[list["Parcel"]] = relationship(back_populates="user")


class Parcel(Base):
    __tablename__ = "parcels"
    __table_args__ = (
        CheckConstraint("status IN ('booked','picked_up','in_transit','out_for_delivery','delivered','cancelled')", name="status_valid"),
        CheckConstraint("weight_kg > 0", name="weight_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    sender_name: Mapped[str] = mapped_column(String(100))
    sender_phone: Mapped[str] = mapped_column(String(20))
    pickup_address: Mapped[str] = mapped_column(String(255))
    pickup_city: Mapped[str] = mapped_column(String(80))

    recipient_name: Mapped[str] = mapped_column(String(100))
    recipient_phone: Mapped[str] = mapped_column(String(20))
    delivery_address: Mapped[str] = mapped_column(String(255))
    delivery_city: Mapped[str] = mapped_column(String(80))

    zone: Mapped[str] = mapped_column(String(16))
    service: Mapped[str] = mapped_column(String(16))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    chargeable_weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    length_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    declared_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), server_default="0")
    fragile: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="booked", server_default="booked", index=True)
    rider_id: Mapped[int | None] = mapped_column(ForeignKey("riders.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("courier_providers.id", ondelete="SET NULL"), nullable=True, index=True)
    price_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_breakdown: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="parcels")
    rider: Mapped["Rider"] = relationship()
    provider: Mapped["CourierProvider"] = relationship()
    events: Mapped[list["TrackingEvent"]] = relationship(
        back_populates="parcel", cascade="all, delete-orphan", order_by="TrackingEvent.id", lazy="selectin"
    )


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parcel: Mapped[Parcel] = relationship(back_populates="events")


class Rider(Base):
    __tablename__ = "riders"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    vehicle: Mapped[str] = mapped_column(String(30), default="bike", server_default="bike")
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourierProvider(Base):
    __tablename__ = "courier_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceArea(Base):
    __tablename__ = "service_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(80), unique=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    """Staff actions shown in the admin 'Recent Activities' feed (bookings and sign-ups are derived, not logged)."""
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
