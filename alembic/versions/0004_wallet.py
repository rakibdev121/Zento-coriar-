"""wallet: user balance, ledger, deposit/withdraw/COD requests, parcel COD and money flags

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_NOW = sa.func.now()


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("balance", sa.Numeric(12, 2), server_default="0", nullable=False))

    with op.batch_alter_table("parcels") as b:
        b.add_column(sa.Column("cod_amount", sa.Numeric(10, 2), server_default="0", nullable=False))
        b.add_column(sa.Column("wallet_paid", sa.Boolean(), server_default=sa.false(), nullable=False))
        b.add_column(sa.Column("refunded", sa.Boolean(), server_default=sa.false(), nullable=False))
        b.add_column(sa.Column("commission_paid", sa.Boolean(), server_default=sa.false(), nullable=False))
        b.add_column(sa.Column("cod_credited", sa.Boolean(), server_default=sa.false(), nullable=False))

    op.create_table(
        "wallet_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(12), nullable=False),
        sa.Column("account", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(60), nullable=True),
        sa.Column("status", sa.String(10), server_default="pending", nullable=False),
        sa.Column("admin_note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_requests"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_wallet_requests_user_id_users", ondelete="RESTRICT"),
    )
    op.create_index("ix_wallet_requests_user_id", "wallet_requests", ["user_id"])
    op.create_index("ix_wallet_requests_status", "wallet_requests", ["status"])
    op.create_index("ix_wallet_requests_created_at", "wallet_requests", ["created_at"])

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(160), nullable=True),
        sa.Column("parcel_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_transactions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_wallet_transactions_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"], name="fk_wallet_transactions_parcel_id_parcels", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["wallet_requests.id"], name="fk_wallet_transactions_request_id_wallet_requests", ondelete="SET NULL"),
    )
    op.create_index("ix_wallet_transactions_user_id", "wallet_transactions", ["user_id"])
    op.create_index("ix_wallet_transactions_created_at", "wallet_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_wallet_transactions_created_at", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_user_id", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")
    op.drop_index("ix_wallet_requests_created_at", table_name="wallet_requests")
    op.drop_index("ix_wallet_requests_status", table_name="wallet_requests")
    op.drop_index("ix_wallet_requests_user_id", table_name="wallet_requests")
    op.drop_table("wallet_requests")
    with op.batch_alter_table("parcels") as b:
        b.drop_column("cod_credited")
        b.drop_column("commission_paid")
        b.drop_column("refunded")
        b.drop_column("wallet_paid")
        b.drop_column("cod_amount")
    with op.batch_alter_table("users") as b:
        b.drop_column("balance")
