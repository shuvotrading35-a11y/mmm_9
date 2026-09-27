"""
User Service — registration, profile management, referral chain setup.
"""
import asyncio
import secrets
import string
from decimal import Decimal
from typing import Optional, Tuple

import structlog
from sqlalchemy import select, func as sa_func
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

        Referral rules:
        - New user with valid referrer_code → create Referral + pay signup reward.
        - Existing user without referrer_id + valid referrer_code → apply late referral
          + pay signup reward (only once, guarded by Referral row check).
        - Self-referral blocked.
        - Reward is paid INLINE within the same transaction so it is atomic.
        """
        from datetime import datetime, timezone

        user = await session.get(User, tg_user.id)

        # ─────────────────────────────────────────────────────────────
        # EXISTING USER: refresh profile + optional late referral
        # ─────────────────────────────────────────────────────────────
        if user:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            user.last_active = datetime.now(tz=timezone.utc)

            applied_late_referral = False

            if referrer_code and user.referrer_id is None:
                result = await session.execute(
                    select(User.id).where(User.referral_code == referrer_code)
                )
                found_id = result.scalar_one_or_none()

                if found_id and found_id != tg_user.id:
                    # Guard against duplicate: no existing Referral row for this user
                    existing = await session.execute(
                        select(Referral.id).where(
                            Referral.referred_id == tg_user.id
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        user.referrer_id = found_id

                        referral = Referral(
                            referrer_id=found_id,
                            referred_id=tg_user.id,
                        )
                        session.add(referral)
                        await session.flush()

                        referrer = await session.get(User, found_id)
                        if referrer:
                            reward = settings.REFERRAL_REWARD
                            referrer.balance = (referrer.balance or Decimal("0")) + reward
                            referral.reward_paid = reward
                            applied_late_referral = True
                            log.info(
                                "Late referral applied + reward paid",
                                referrer_id=found_id,
                                referred_id=tg_user.id,
                                amount=str(reward),
                            )

            await session.flush()

            if applied_late_referral:
                _referrer_id = user.referrer_id
                asyncio.create_task(
                    UserService._notify_referral_joined(_referrer_id)
                )

            return user, False

        # ─────────────────────────────────────────────────────────────
        # NEW USER: resolve referrer
        # ─────────────────────────────────────────────────────────────
        referrer_id: Optional[int] = None
        if referrer_code:
            result = await session.execute(
                select(User.id).where(User.referral_code == referrer_code)
            )
            found_id = result.scalar_one_or_none()
            if found_id and found_id != tg_user.id:
                referrer_id = found_id

        # ─────────────────────────────────────────────────────────────
        # Create new user
        # ─────────────────────────────────────────────────────────────
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

        # ─────────────────────────────────────────────────────────────
        # Notify admins of new registration (background, no DB)
        # ─────────────────────────────────────────────────────────────
        try:
            total_users = (await session.execute(
                select(sa_func.count(User.id))
            )).scalar()

            from services.notification_service import NotificationService
            asyncio.create_task(
                NotificationService.notify_admin_new_user(
                    user_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    referrer_id=referrer_id,
                    total_users=total_users,
                    language_code=getattr(tg_user, "language_code", None),
                    is_premium=bool(getattr(tg_user, "is_premium", False)),
                )
            )
        except Exception:
            log.exception("Failed to notify admins of new user")

        # ─────────────────────────────────────────────────────────────
        # Create referral row + pay signup reward INLINE (atomic)
        # ─────────────────────────────────────────────────────────────
        if referrer_id:
            referral = Referral(
                referrer_id=referrer_id,
                referred_id=tg_user.id,
            )
            session.add(referral)
            await session.flush()

            referrer = await session.get(User, referrer_id)
            if referrer:
                reward = settings.REFERRAL_REWARD
                referrer.balance = (referrer.balance or Decimal("0")) + reward
                referral.reward_paid = reward
                log.info(
                    "Signup referral reward paid",
                    referrer_id=referrer_id,
                    referred_id=tg_user.id,
                    amount=str(reward),
                )

            asyncio.create_task(
                UserService._notify_referral_joined(referrer_id)
            )

        log.info(
            "New user registered",
            user_id=tg_user.id,
            username=tg_user.username,
            referrer_id=referrer_id,
        )
        return user, True

    # ─────────────────────────────────────────────────────────────
    # Background notification helper (does NOT touch DB transaction)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    async def _notify_referral_joined(referrer_id: int) -> None:
        """Fire-and-forget notification when someone uses a referral link."""
        try:
            from services.notification_service import NotificationService
            await NotificationService.referral_joined(
                referrer_id, str(settings.REFERRAL_REWARD)
            )
        except Exception as e:
            log.error("Referral notification failed", error=str(e))

    # ─────────────────────────────────────────────────────────────
    # Read helpers
    # ─────────────────────────────────────────────────────────────
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

    # ─────────────────────────────────────────────────────────────
    # BSC wallet
    # ─────────────────────────────────────────────────────────────
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

        user = await session.get(User, user_id)
        if user:
            user.bsc_wallet = checksummed
            await session.flush()

            from models.wallet import Wallet
            wallet = Wallet(
                user_id=user_id,
                address=checksummed.lower(),
                is_active=True,
            )
            session.add(wallet)
            await session.flush()

    # ─────────────────────────────────────────────────────────────
    # Referral stats
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    async def get_referral_stats(
        session: AsyncSession, user_id: int
    ) -> dict:
        """Get referral statistics for a user."""
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