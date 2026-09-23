import enum
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, String, Text, Enum, Numeric,
    DateTime, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EntityType(str, enum.Enum):
    USER = "USER"
    SPONSOR = "SPONSOR"
    PLATFORM = "PLATFORM"


class TransactionType(str, enum.Enum):
    TASK_REWARD = "TASK_REWARD"
    REFERRAL_REWARD = "REFERRAL_REWARD"
    REFERRAL_COMMISSION = "REFERRAL_COMMISSION"
    WITHDRAWAL = "WITHDRAWAL"
    WITHDRAWAL_RETURN = "WITHDRAWAL_RETURN"
    DEPOSIT = "DEPOSIT"
    CAMPAIGN_FUND = "CAMPAIGN_FUND"
    CAMPAIGN_RELEASE = "CAMPAIGN_RELEASE"
    ADMIN_CREDIT = "ADMIN_CREDIT"
    ADMIN_DEBIT = "ADMIN_DEBIT"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="entity_type"), nullable=False
    )
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_transactions_entity", "entity_type", "entity_id"),
        Index("idx_transactions_created", "created_at"),
        Index("idx_transactions_idempotency", "idempotency_key"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} type={self.tx_type} "
            f"amount={self.amount} entity={self.entity_type}:{self.entity_id}>"
        )
