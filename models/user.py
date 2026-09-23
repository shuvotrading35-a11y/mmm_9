"""
User model — core account entity.
"""
import enum
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, String, Enum, Numeric, Integer,
    Boolean, DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.referral import Referral
    from models.transaction import Transaction
    from models.withdrawal import Withdrawal
    from models.task_completion import TaskCompletion
    from models.fraud_flag import FraudFlag
    from models.wallet import Wallet


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FLAGGED = "FLAGGED"
    RESTRICTED = "RESTRICTED"
    BANNED = "BANNED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.ACTIVE,
        nullable=False
    )
    fraud_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Financial
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    total_earned: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    total_withdrawn: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )

    # Activity
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Wallet
    bsc_wallet: Mapped[Optional[str]] = mapped_column(String(42), nullable=True)

    # Referral
    referrer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    # Roles
    is_sponsor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    joined_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    referrer: Mapped[Optional["User"]] = relationship(
        "User", remote_side="User.id", foreign_keys=[referrer_id]
    )
    referrals_made: Mapped[List["Referral"]] = relationship(
        "Referral", foreign_keys="Referral.referrer_id", back_populates="referrer"
    )
    referral_as_referred: Mapped[Optional["Referral"]] = relationship(
        "Referral", foreign_keys="Referral.referred_id", back_populates="referred", uselist=False
    )
    task_completions: Mapped[List["TaskCompletion"]] = relationship(
        "TaskCompletion", back_populates="user"
    )
    withdrawals: Mapped[List["Withdrawal"]] = relationship(
        "Withdrawal", back_populates="user"
    )
    fraud_flags: Mapped[List["FraudFlag"]] = relationship(
        "FraudFlag", back_populates="user"
    )

    __table_args__ = (
        Index("idx_users_referrer", "referrer_id"),
        Index("idx_users_status", "status"),
        Index("idx_users_referral_code", "referral_code"),
        Index("idx_users_bsc_wallet", "bsc_wallet"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} status={self.status}>"

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        full = " ".join(filter(None, [self.first_name, self.last_name]))
        return full or f"User {self.id}"

    @property
    def masked_id(self) -> str:
        """Mask user ID for public display."""
        s = str(self.id)
        return f"****{s[-4:]}" if len(s) >= 4 else "****"
