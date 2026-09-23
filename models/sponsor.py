import enum
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Integer, BigInteger, String, Enum, Numeric,
    DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.user import User
    from models.campaign import Campaign
    from models.deposit import Deposit


class SponsorStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    BANNED = "BANNED"


class Sponsor(Base):
    __tablename__ = "sponsors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    company_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[SponsorStatus] = mapped_column(
        Enum(SponsorStatus, name="sponsor_status"),
        default=SponsorStatus.PENDING,
        nullable=False
    )

    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    reserved_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    total_deposited: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    total_spent: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )

    approved_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    campaigns: Mapped[List["Campaign"]] = relationship("Campaign", back_populates="sponsor")
    deposits: Mapped[List["Deposit"]] = relationship("Deposit", back_populates="sponsor")

    __table_args__ = (
        Index("idx_sponsors_status", "status"),
        Index("idx_sponsors_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Sponsor id={self.id} user_id={self.user_id} status={self.status}>"
