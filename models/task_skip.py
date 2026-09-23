from typing import TYPE_CHECKING
from sqlalchemy import (
    BigInteger, Integer, DateTime, ForeignKey,
    UniqueConstraint, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.user import User
    from models.campaign import Campaign


class TaskSkip(Base):
    __tablename__ = "task_skips"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    skipped_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="skips")

    __table_args__ = (
        UniqueConstraint("user_id", "campaign_id", name="uq_skip_user_campaign"),
        Index("idx_task_skips_user", "user_id"),
    )
