"""
User Service — registration, profile management, referral chain setup.
"""
import secrets
import string
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import User as TGUser

from config import settings
from models.referral import Referral
from models.user import User, UserStatus

log = structlog.get_logger(__name__)


def _generate_referral_code(user_id: int) -> str:
    """Generate a unique referral code for a user."""
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"REF{user_id}{suffix}"


class UserService:

    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        tg_user: TGUser,
        referrer_code: Optional[str] = None,
    ) -> Tuple["User", bool]:
        """
        Get existing user or create new one.
        Returns (user, is_new).
        """
        from typing import Tuple

        user = await session.get(User, tg_user.id)
        if user:
            # Update profile data
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            from datetime import datetime, timezone
            user.last_active = datetime.now(tz=timezone.utc)
            await session.flush()
            return user, False

        # Resolve referrer
        referrer_id: Optional[int] = None
        if referrer_code:
            result = await session.execute(
                select(User.id).where(User.referral_code == referrer_code)
            )
            found_id = result.scalar_one_or_none()
            if found_id and found_id != tg_user.id:
                referrer_id = found_id

        # Create new user
        referral_code = _generate_referral_code(tg_user.id)
        user = User(
            id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            referral_code=referral_code,
            referrer_id=referrer_id,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()

        # Create referral record and pay reward
        if referrer_id:
            referral = Referral(
                referrer_id=referrer_id,
                referred_id=tg_user.id,
            )
            session.add(referral)
            await session.flush()

            # Pay referral signup reward
            from services.reward_service import RewardService
            import asyncio
            asyncio.create_task(
                UserService._pay_referral_reward_async(referrer_id, tg_user.id)
            )

        log.info(
            "New user registered",
            user_id=tg_user.id,
            username=tg_user.username,
            referrer_id=referrer_id,
        )
        return user, True

    @staticmethod
    async def _pay_referral_reward_async(referrer_id: int, referred_id: int) -> None:
        """Pay referral signup reward in a separate transaction."""
        from database import get_session
        from services.reward_service import RewardService
        try:
            async with get_session() as session:
                async with session.begin():
                    await RewardService.pay_referral_signup_reward(
                        session=session,
                        referrer_id=referrer_id,
                        referred_user_id=referred_id,
                    )
            # Notify referrer
            from services.notification_service import NotificationService
            await NotificationService.referral_joined(
                referrer_id, settings.REFERRAL_REWARD
            )
        except Exception as e:
            log.error("Referral reward payment failed", error=str(e))

    @staticmethod
    async def get_user(session: AsyncSession, user_id: int) -> Optional[User]:
        return await session.get(User, user_id)

    @staticmethod
    async def get_user_by_referral_code(
        session: AsyncSession, code: str
    ) -> Optional[User]:
        result = await session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def set_bsc_wallet(
        session: AsyncSession,
        user_id: int,
        wallet_address: str,
    ) -> None:
        """Set/update a user's BSC wallet address after validation."""
        from utils.wallet_utils import validate_bsc_address, checksum_address
        if not validate_bsc_address(wallet_address):
            raise ValueError("Invalid BSC wallet address")

        checksummed = checksum_address(wallet_address)

        # Check for duplicate wallet (fraud check)
        from services.fraud_service import FraudService
        from database import get_session as gs

        user = await session.get(User, user_id)
        if user:
            user.bsc_wallet = checksummed
            await session.flush()

            # Record in wallets table for duplicate detection
            from models.wallet import Wallet
            wallet = Wallet(
                user_id=user_id,
                address=checksummed.lower(),
                is_active=True,
            )
            session.add(wallet)
            await session.flush()

    @staticmethod
    async def get_referral_stats(
        session: AsyncSession, user_id: int
    ) -> dict:
        """Get referral statistics for a user."""
        from models.referral import Referral
        from sqlalchemy import func as sa_func

        result = await session.execute(
            select(
                sa_func.count(Referral.id).label("total"),
                sa_func.coalesce(sa_func.sum(Referral.commission_earned), 0).label("commission"),
                sa_func.coalesce(sa_func.sum(Referral.reward_paid), 0).label("signup_rewards"),
            ).where(Referral.referrer_id == user_id)
        )
        row = result.one()
        return {
            "total_referrals": row.total or 0,
            "commission_earned": row.commission or 0,
            "signup_rewards": row.signup_rewards or 0,
        }
