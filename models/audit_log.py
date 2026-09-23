from typing import Optional, Any, Dict
from sqlalchemy import (
    BigInteger, String, DateTime, func, Index
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    old_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_audit_logs_admin", "admin_id"),
        Index("idx_audit_logs_target", "target_type", "target_id"),
        Index("idx_audit_logs_created", "created_at"),
    )