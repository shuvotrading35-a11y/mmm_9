import enum
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Integer, BigInteger, String, Enum, Numeric,
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
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True, nullable=False)
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

    sponsor: Mapped["Sponsor"] = relationship("Sponsor", back_populates="deposits")

    __table_args__ = (
        Index("idx_deposits_sponsor", "sponsor_id"),
        Index("idx_deposits_status", "status"),
        Index("idx_deposits_tx_hash", "tx_hash"),
    )
