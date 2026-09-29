"""Add xRocket Pay API fields to withdrawals.

Revision ID: 002_xrocket_withdrawals
Revises: 001_initial
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = '002_xrocket_withdrawals'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "withdrawals",
        sa.Column("xrocket_withdrawal_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "withdrawals",
        sa.Column("xrocket_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "withdrawals",
        sa.Column("xrocket_response", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_withdrawals_xrocket_id",
        "withdrawals",
        ["xrocket_withdrawal_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawals_xrocket_id", table_name="withdrawals")
    op.drop_column("withdrawals", "xrocket_response")
    op.drop_column("withdrawals", "xrocket_status")
    op.drop_column("withdrawals", "xrocket_withdrawal_id")