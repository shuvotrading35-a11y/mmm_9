import enum
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Integer, BigInteger, String, Text, Enum, Numeric,
    DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.sponsor import Sponsor
    from models.task_completion import TaskCompletion
    from models.task_skip import TaskSkip


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    PENDING_FUNDING = "PENDING_FUNDING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class TaskType(str, enum.Enum):
    CHANNEL_JOIN = "CHANNEL_JOIN"
    GROUP_JOIN = "GROUP_JOIN"
    BOT_START = "BOT_START"
    CHANNEL_GROUP_JOIN = "CHANNEL_GROUP_JOIN"
    FORCE_JOIN = "FORCE_JOIN"
    CUSTOM = "CUSTOM"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sponsor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sponsors.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="task_type"), nullable=False
    )

    # Telegram target
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    invite_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Financial
    reward_per_user: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    completion_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_budget: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    reserved_budget: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    spent_budget: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )

    # Analytics
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_verify_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"),
        default=CampaignStatus.DRAFT,
        nullable=False
    )
    approved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    sponsor: Mapped["Sponsor"] = relationship("Sponsor", back_populates="campaigns")
    completions: Mapped[List["TaskCompletion"]] = relationship(
        "TaskCompletion", back_populates="campaign"
    )
    skips: Mapped[List["TaskSkip"]] = relationship("TaskSkip", back_populates="campaign")

    __table_args__ = (
        Index("idx_campaigns_status", "status"),
        Index("idx_campaigns_sponsor", "sponsor_id"),
        Index("idx_campaigns_expires", "expires_at"),
    )

    @property
    def remaining_budget(self) -> Decimal:
        return self.total_budget - self.spent_budget

    @property
    def remaining_slots(self) -> int:
        return self.completion_limit - self.completed_count

    @property
    def is_funded(self) -> bool:
        return self.reserved_budget >= self.total_budget

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} title={self.title!r} status={self.status}>"
