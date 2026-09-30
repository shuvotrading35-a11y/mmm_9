"""Add manual deposit fields (Binance Pay + BEP20)."""
from alembic import op
import sqlalchemy as sa

revision = '004_manual_deposits'
down_revision = '003_xrocket_deposits'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deposits", sa.Column("deposit_address", sa.String(128), nullable=True))
    op.add_column("deposits", sa.Column("user_screenshot_file_id", sa.String(256), nullable=True))
    op.add_column("deposits", sa.Column("user_submitted_tx_hash", sa.String(66), nullable=True))
    op.add_column("deposits", sa.Column("reviewed_by", sa.BigInteger(), nullable=True))
    op.add_column("deposits", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deposits", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("deposits", "rejection_reason")
    op.drop_column("deposits", "reviewed_at")
    op.drop_column("deposits", "reviewed_by")
    op.drop_column("deposits", "user_submitted_tx_hash")
    op.drop_column("deposits", "user_screenshot_file_id")
    op.drop_column("deposits", "deposit_address")