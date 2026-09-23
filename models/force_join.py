from typing import Optional
from sqlalchemy import Integer, BigInteger, String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class ForceJoinChannel(Base):
    __tablename__ = "force_join_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    invite_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ForceJoinChannel id={self.id} chat_id={self.chat_id}>"
