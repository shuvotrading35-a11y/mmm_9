"""Add xRocket invoice fields to deposits."""
from alembic import op
import sqlalchemy as sa

revision = '003_xrocket_deposits'
down_revision = '002_xrocket_withdrawals'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deposits", sa.Column("payment_method", sa.String(32), nullable=False, server_default="ONCHAIN"))
    op.add_column("deposits", sa.Column("xrocket_invoice_id", sa.String(64), nullable=True))
    op.add_column("deposits", sa.Column("xrocket_client_invoice_id", sa.String(64), nullable=True, unique=True))
    op.add_column("deposits", sa.Column("xrocket_pay_url", sa.Text(), nullable=True))
    op.add_column("deposits", sa.Column("xrocket_status", sa.String(32), nullable=True))
    op.add_column("deposits", sa.Column("xrocket_response", sa.Text(), nullable=True))
    op.create_index("ix_deposits_xrocket_invoice_id", "deposits", ["xrocket_invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_deposits_xrocket_invoice_id", table_name="deposits")
    op.drop_column("deposits", "xrocket_response")
    op.drop_column("deposits", "xrocket_status")
    op.drop_column("deposits", "xrocket_pay_url")
    op.drop_column("deposits", "xrocket_client_invoice_id")
    op.drop_column("deposits", "xrocket_invoice_id")
    op.drop_column("deposits", "payment_method")