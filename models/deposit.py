import enum
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Integer, BigInteger, String, Text, Enum, Numeric,
    DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.sponsor import Sponsor


class DepositStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class Deposit(Base):
    __tablename__ = "deposits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sponsor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sponsors.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    network: Mapped[str] = mapped_column(String(16), default="BSC", nullable=False)

    # ── On-chain tx hash (nullable — not all methods use on-chain) ──
    tx_hash: Mapped[Optional[str]] = mapped_column(
        String(66), unique=True, nullable=True
    )
    from_address: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)
    block_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[DepositStatus] = mapped_column(
        Enum(DepositStatus, name="deposit_status"),
        default=DepositStatus.PENDING,
        nullable=False
    )
    credited_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ══════════════════════════════════════════════════════════════
    # ── Deposit method ──
    # ══════════════════════════════════════════════════════════════
    # Values: ONCHAIN, XROCKET_INVOICE, BINANCE_PAY, BEP20
    payment_method: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ONCHAIN"
    )

    # ══════════════════════════════════════════════════════════════
    # ── xRocket Invoice fields ──
    # ══════════════════════════════════════════════════════════════
    xrocket_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    xrocket_client_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True
    )
    xrocket_pay_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    xrocket_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    xrocket_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ══════════════════════════════════════════════════════════════
    # ── Manual deposit fields (Binance Pay + BEP20) ──
    # ══════════════════════════════════════════════════════════════
    deposit_address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_screenshot_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    user_submitted_tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)

    # Admin review
    reviewed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sponsor: Mapped["Sponsor"] = relationship("Sponsor", back_populates="deposits")

    __table_args__ = (
        Index("idx_deposits_sponsor", "sponsor_id"),
        Index("idx_deposits_status", "status"),
        Index("idx_deposits_tx_hash", "tx_hash"),
        Index("idx_deposits_payment_method", "payment_method"),
    )