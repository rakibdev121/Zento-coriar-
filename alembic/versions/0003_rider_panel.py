"""rider panel: rider applications and documents, parcel rider response, commission and delivery time

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    with op.batch_alter_table("riders") as b:
        b.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        b.add_column(sa.Column("status", sa.String(12), server_default="approved", nullable=False))  # existing riders stay approved
        b.add_column(sa.Column("id_type", sa.String(12), nullable=True))
        b.add_column(sa.Column("id_number", sa.String(40), nullable=True))
        b.add_column(sa.Column("reject_reason", sa.String(255), nullable=True))
        b.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        b.create_foreign_key("fk_riders_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL")
        b.create_unique_constraint("uq_riders_user_id", ["user_id"])

    op.create_table(
        "rider_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rider_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(20), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rider_documents"),
        sa.ForeignKeyConstraint(["rider_id"], ["riders.id"], name="fk_rider_documents_rider_id_riders", ondelete="CASCADE"),
        sa.UniqueConstraint("rider_id", "kind", name="uq_rider_documents_rider_id"),
    )
    op.create_index("ix_rider_documents_rider_id", "rider_documents", ["rider_id"])

    with op.batch_alter_table("parcels") as b:
        b.add_column(sa.Column("rider_response", sa.String(10), nullable=True))
        b.add_column(sa.Column("rider_assigned_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("rider_note", sa.String(255), nullable=True))
        b.add_column(sa.Column("rider_commission", sa.Numeric(10, 2), nullable=True))
        b.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("parcels") as b:
        b.drop_column("delivered_at")
        b.drop_column("rider_commission")
        b.drop_column("rider_note")
        b.drop_column("rider_assigned_at")
        b.drop_column("rider_response")
    op.drop_index("ix_rider_documents_rider_id", table_name="rider_documents")
    op.drop_table("rider_documents")
    with op.batch_alter_table("riders") as b:
        b.drop_constraint("uq_riders_user_id", type_="unique")
        b.drop_constraint("fk_riders_user_id_users", type_="foreignkey")
        b.drop_column("reviewed_at")
        b.drop_column("reject_reason")
        b.drop_column("id_number")
        b.drop_column("id_type")
        b.drop_column("status")
        b.drop_column("user_id")
