import enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger, String, Enum, DateTime, ForeignKey, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

if TYPE_CHECKING:
    from models.user import User


class TicketCategory(str, enum.Enum):
    PAYMENT = "PAYMENT"
    TASK = "TASK"
    WITHDRAWAL = "WITHDRAWAL"
    REFERRAL = "REFERRAL"
    OTHER = "OTHER"


class TicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[TicketCategory] = mapped_column(
        Enum(TicketCategory, name="ticket_category"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"),
        default=TicketStatus.OPEN,
        nullable=False
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("idx_support_tickets_user", "user_id"),
        Index("idx_support_tickets_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<SupportTicket {self.ticket_code} status={self.status}>"
