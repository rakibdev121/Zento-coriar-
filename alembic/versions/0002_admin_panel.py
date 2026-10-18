"""admin panel: users.is_admin, riders, courier_providers, service_areas, activity_log, parcel assignment

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    op.create_table(
        "riders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("vehicle", sa.String(30), server_default="bike", nullable=False),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_riders"),
    )
    op.create_table(
        "courier_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("website", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_courier_providers"),
        sa.UniqueConstraint("name", name="uq_courier_providers_name"),
    )
    op.create_table(
        "service_areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("region", sa.String(80), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_service_areas"),
        sa.UniqueConstraint("city", name="uq_service_areas_city"),
    )
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("detail", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_activity_log"),
    )
    op.create_index("ix_activity_log_created_at", "activity_log", ["created_at"])

    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    with op.batch_alter_table("parcels") as b:
        b.add_column(sa.Column("rider_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("provider_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_parcels_rider_id_riders", "riders", ["rider_id"], ["id"], ondelete="SET NULL")
        b.create_foreign_key("fk_parcels_provider_id_courier_providers", "courier_providers", ["provider_id"], ["id"], ondelete="SET NULL")
        b.create_index("ix_parcels_rider_id", ["rider_id"])
        b.create_index("ix_parcels_provider_id", ["provider_id"])


def downgrade() -> None:
    with op.batch_alter_table("parcels") as b:
        b.drop_index("ix_parcels_provider_id")
        b.drop_index("ix_parcels_rider_id")
        b.drop_constraint("fk_parcels_provider_id_courier_providers", type_="foreignkey")
        b.drop_constraint("fk_parcels_rider_id_riders", type_="foreignkey")
        b.drop_column("provider_id")
        b.drop_column("rider_id")
    with op.batch_alter_table("users") as b:
        b.drop_column("is_admin")
    op.drop_index("ix_activity_log_created_at", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_table("service_areas")
    op.drop_table("courier_providers")
    op.drop_table("riders")
