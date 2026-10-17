"""initial schema: users, parcels, tracking_events

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "parcels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tracking_number", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sender_name", sa.String(100), nullable=False),
        sa.Column("sender_phone", sa.String(20), nullable=False),
        sa.Column("pickup_address", sa.String(255), nullable=False),
        sa.Column("pickup_city", sa.String(80), nullable=False),
        sa.Column("recipient_name", sa.String(100), nullable=False),
        sa.Column("recipient_phone", sa.String(20), nullable=False),
        sa.Column("delivery_address", sa.String(255), nullable=False),
        sa.Column("delivery_city", sa.String(80), nullable=False),
        sa.Column("zone", sa.String(16), nullable=False),
        sa.Column("service", sa.String(16), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("chargeable_weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("length_cm", sa.Integer(), nullable=True),
        sa.Column("width_cm", sa.Integer(), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("declared_value", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("fragile", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), server_default="booked", nullable=False),
        sa.Column("price_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_breakdown", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('booked','picked_up','in_transit','out_for_delivery','delivered','cancelled')",
            name=op.f("ck_parcels_status_valid"),
        ),
        sa.CheckConstraint("weight_kg > 0", name=op.f("ck_parcels_weight_positive")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_parcels_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_parcels"),
    )
    op.create_index("ix_parcels_tracking_number", "parcels", ["tracking_number"], unique=True)
    op.create_index("ix_parcels_user_id", "parcels", ["user_id"])
    op.create_index("ix_parcels_status", "parcels", ["status"])

    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parcel_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(255), nullable=False),
        sa.Column("location", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"], name="fk_tracking_events_parcel_id_parcels", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_tracking_events"),
    )
    op.create_index("ix_tracking_events_parcel_id", "tracking_events", ["parcel_id"])


def downgrade() -> None:
    op.drop_index("ix_tracking_events_parcel_id", table_name="tracking_events")
    op.drop_table("tracking_events")
    op.drop_index("ix_parcels_status", table_name="parcels")
    op.drop_index("ix_parcels_user_id", table_name="parcels")
    op.drop_index("ix_parcels_tracking_number", table_name="parcels")
    op.drop_table("parcels")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
