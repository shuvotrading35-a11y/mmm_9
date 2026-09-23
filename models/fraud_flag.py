import enum
from typing import Optional, Any, Dict, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, Boolean, Enum, DateTime,
    ForeignKey, func, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.user import User


class FlagType(str, enum.Enum):
    DUPLICATE_ACCOUNT = "DUPLICATE_ACCOUNT"
    RAPID_COMPLETION = "RAPID_COMPLETION"
    SUSPICIOUS_REFERRAL = "SUSPICIOUS_REFERRAL"
    DUPLICATE_WALLET = "DUPLICATE_WALLET"
    EXCESSIVE_WITHDRAWAL = "EXCESSIVE_WITHDRAWAL"
    BOT_BEHAVIOR = "BOT_BEHAVIOR"
    ABNORMAL_GROWTH = "ABNORMAL_GROWTH"
    REFERRAL_SELF_CHAIN = "REFERRAL_SELF_CHAIN"
    MULTIPLE_IPS = "MULTIPLE_IPS"
    EARLY_WITHDRAWAL = "EARLY_WITHDRAWAL"


class FlagSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FraudFlag(Base):
    __tablename__ = "fraud_flags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    flag_type: Mapped[FlagType] = mapped_column(
        Enum(FlagType, name="flag_type"), nullable=False
    )
    severity: Mapped[FlagSeverity] = mapped_column(
        Enum(FlagSeverity, name="flag_severity"), nullable=False
    )
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="fraud_flags")

    __table_args__ = (
        Index("idx_fraud_flags_user", "user_id"),
        Index("idx_fraud_flags_reviewed", "reviewed"),
        Index("idx_fraud_flags_severity", "severity"),
    )
