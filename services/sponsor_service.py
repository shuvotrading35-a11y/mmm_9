"""
Sponsor Service — sponsor account management and registration.
"""
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sponsor import Sponsor, SponsorStatus
from models.user import User

log = structlog.get_logger(__name__)


class SponsorService:

    @staticmethod
    async def apply_for_sponsor(
        session: AsyncSession,
        user_id: int,
        company_name: Optional[str] = None,
    ) -> Sponsor:
        """Submit a sponsor application (PENDING status)."""
        # Check existing application
        existing = await session.execute(
            select(Sponsor).where(Sponsor.user_id == user_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError("You already have a sponsor application")

        sponsor = Sponsor(
            user_id=user_id,
            company_name=company_name,
            status=SponsorStatus.PENDING,
        )
        session.add(sponsor)

        # Mark user as sponsor
        user = await session.get(User, user_id)
        if user:
            user.is_sponsor = True

        await session.flush()

        # Notify admin
        from services.notification_service import NotificationService
        import asyncio
        asyncio.create_task(
            NotificationService.notify_admin_critical(
                f"New sponsor application from user {user_id}: {company_name or 'No company name'}"
            )
        )

        log.info("Sponsor application submitted", user_id=user_id)
        return sponsor

    @staticmethod
    async def approve_sponsor(
        session: AsyncSession,
        sponsor_id: int,
        admin_id: int,
    ) -> Sponsor:
        """Admin approves a sponsor account."""
        from datetime import datetime, timezone

        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            raise ValueError("Sponsor not found")
        if sponsor.status != SponsorStatus.PENDING:
            raise ValueError(f"Cannot approve sponsor in status {sponsor.status}")

        sponsor.status = SponsorStatus.APPROVED
        sponsor.approved_by = admin_id
        sponsor.approved_at = datetime.now(tz=timezone.utc)
        await session.flush()

        log.info("Sponsor approved", sponsor_id=sponsor_id, admin_id=admin_id)
        return sponsor

    @staticmethod
    async def get_sponsor_by_user(
        session: AsyncSession, user_id: int
    ) -> Optional[Sponsor]:
        result = await session.execute(
            select(Sponsor).where(Sponsor.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_sponsor_wallet_info(
        session: AsyncSession, sponsor_id: int
    ) -> dict:
        from config import settings
        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            return {}
        return {
            "deposit_address": settings.PAYOUT_WALLET_ADDRESS,
            "network": "BNB Smart Chain (BSC)",
            "token": "USDT (BEP-20)",
            "contract": settings.USDT_CONTRACT_ADDRESS,
            "minimum_deposit": str(settings.SPONSOR_MIN_DEPOSIT),
            "available_balance": sponsor.available_balance,
            "reserved_balance": sponsor.reserved_balance,
            "total_deposited": sponsor.total_deposited,
            "total_spent": sponsor.total_spent,
        }
