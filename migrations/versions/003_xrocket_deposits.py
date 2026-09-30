"""Add xRocket invoice fields + make tx_hash nullable."""
from alembic import op
import sqlalchemy as sa

revision = '003_xrocket_deposits'
down_revision = '002_xrocket_withdrawals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── tx_hash must be nullable now (not all deposits have on-chain hash) ──
    op.alter_column(
        "deposits", "tx_hash",
        existing_type=sa.String(66),
        nullable=True,
    )

    # ── payment_method ──
    op.add_column(
        "deposits",
        sa.Column("payment_method", sa.String(32), nullable=False, server_default="ONCHAIN"),
    )

    # ── xRocket invoice fields ──
    op.add_column("deposits", sa.Column("xrocket_invoice_id", sa.String(64), nullable=True))
    op.add_column("deposits", sa.Column("xrocket_client_invoice_id", sa.String(64), nullable=True, unique=True))
    op.add_column("deposits", sa.Column("xrocket_pay_url", sa.Text(), nullable=True))
    op.add_column("deposits", sa.Column("xrocket_status", sa.String(32), nullable=True))
    op.add_column("deposits", sa.Column("xrocket_response", sa.Text(), nullable=True))

    # ── Manual deposit fields ──
    op.add_column("deposits", sa.Column("deposit_address", sa.String(128), nullable=True))
    op.add_column("deposits", sa.Column("user_screenshot_file_id", sa.String(256), nullable=True))
    op.add_column("deposits", sa.Column("user_submitted_tx_hash", sa.String(66), nullable=True))
    op.add_column("deposits", sa.Column("reviewed_by", sa.BigInteger(), nullable=True))
    op.add_column("deposits", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deposits", sa.Column("rejection_reason", sa.Text(), nullable=True))

    # ── Indexes ──
    op.create_index("ix_deposits_xrocket_invoice_id", "deposits", ["xrocket_invoice_id"])
    op.create_index("ix_deposits_payment_method", "deposits", ["payment_method"])


def downgrade() -> None:
    op.drop_index("ix_deposits_payment_method", table_name="deposits")
    op.drop_index("ix_deposits_xrocket_invoice_id", table_name="deposits")
    op.drop_column("deposits", "rejection_reason")
    op.drop_column("deposits", "reviewed_at")
    op.drop_column("deposits", "reviewed_by")
    op.drop_column("deposits", "user_submitted_tx_hash")
    op.drop_column("deposits", "user_screenshot_file_id")
    op.drop_column("deposits", "deposit_address")
    op.drop_column("deposits", "xrocket_response")
    op.drop_column("deposits", "xrocket_status")
    op.drop_column("deposits", "xrocket_pay_url")
    op.drop_column("deposits", "xrocket_client_invoice_id")
    op.drop_column("deposits", "xrocket_invoice_id")
    op.drop_column("deposits", "payment_method")
    op.alter_column(
        "deposits", "tx_hash",
        existing_type=sa.String(66),
        nullable=False,
    )