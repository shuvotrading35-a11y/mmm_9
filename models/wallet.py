from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    BigInteger, String, Boolean, DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.user import User


class Wallet(Base):
    """Tracks verified BSC wallets — used for duplicate detection."""
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    address: Mapped[str] = mapped_column(String(42), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verified_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("idx_wallets_user", "user_id"),
        Index("idx_wallets_address", "address"),
    )
