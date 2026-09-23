from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, Integer, String, Numeric,
    DateTime, ForeignKey, UniqueConstraint, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.user import User
    from models.campaign import Campaign


class TaskCompletion(Base):
    __tablename__ = "task_completions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    membership_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    verified_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="task_completions")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="completions")

    __table_args__ = (
        UniqueConstraint("user_id", "campaign_id", name="uq_completion_user_campaign"),
        Index("idx_task_completions_user", "user_id"),
        Index("idx_task_completions_campaign", "campaign_id"),
    )

    def __repr__(self) -> str:
        return f"<TaskCompletion user={self.user_id} campaign={self.campaign_id}>"
