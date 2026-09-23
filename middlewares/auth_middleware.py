"""
Auth Middleware — resolve user role (USER / SPONSOR / ADMIN).
"""
import enum
from typing import Optional

from config import settings


class UserRole(str, enum.Enum):
    USER = "USER"
    SPONSOR = "SPONSOR"
    ADMIN = "ADMIN"


class AuthMiddleware:

    @staticmethod
    async def get_role(user_id: int) -> UserRole:
        """Resolve the role of a Telegram user ID."""
        if settings.is_admin(user_id):
            return UserRole.ADMIN

        from database import get_session
        from models.sponsor import Sponsor, SponsorStatus
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(Sponsor).where(
                    Sponsor.user_id == user_id,
                    Sponsor.status == SponsorStatus.APPROVED,
                )
            )
            if result.scalar_one_or_none():
                return UserRole.SPONSOR

        return UserRole.USER

    @staticmethod
    def require_admin(user_id: int) -> bool:
        """Quick admin check without DB call."""
        return settings.is_admin(user_id)
