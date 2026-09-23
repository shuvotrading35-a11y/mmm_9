import enum
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, String, Text, Enum, Numeric,
    DateTime, ForeignKey, SmallInteger, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.user import User


class WithdrawalStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    network: Mapped[str] = mapped_column(String(16), default="BSC", nullable=False)
    destination_wallet: Mapped[str] = mapped_column(String(42), nullable=False)

    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus, name="withdrawal_status"),
        default=WithdrawalStatus.PENDING,
        nullable=False
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    block_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    gas_used: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="withdrawals")

    __table_args__ = (
        Index("idx_withdrawals_status", "status"),
        Index("idx_withdrawals_user", "user_id"),
        Index("idx_withdrawals_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Withdrawal id={self.id} amount={self.amount} status={self.status}>"
