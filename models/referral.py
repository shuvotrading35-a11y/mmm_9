from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import (
    BigInteger, Numeric, DateTime, ForeignKey,
    UniqueConstraint, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.user import User


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referred_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    reward_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    commission_earned: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    referrer: Mapped["User"] = relationship(
        "User", foreign_keys=[referrer_id], back_populates="referrals_made"
    )
    referred: Mapped["User"] = relationship(
        "User", foreign_keys=[referred_id], back_populates="referral_as_referred"
    )

    __table_args__ = (
        Index("idx_referrals_referrer", "referrer_id"),
        Index("idx_referrals_referred", "referred_id"),
    )
