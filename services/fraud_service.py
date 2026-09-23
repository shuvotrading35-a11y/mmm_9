"""
Fraud Detection Service — signal-based fraud scoring.
Score 0-100. Auto-actions at configurable thresholds.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.fraud_flag import FraudFlag, FlagType, FlagSeverity
from models.task_completion import TaskCompletion
from models.user import User, UserStatus
from models.wallet import Wallet
from models.withdrawal import Withdrawal, WithdrawalStatus

log = structlog.get_logger(__name__)

# Signal weights
SIGNAL_WEIGHTS = {
    FlagType.DUPLICATE_ACCOUNT: 25,
    FlagType.RAPID_COMPLETION: 15,
    FlagType.SUSPICIOUS_REFERRAL: 30,
    FlagType.DUPLICATE_WALLET: 20,
    FlagType.EXCESSIVE_WITHDRAWAL: 10,
    FlagType.BOT_BEHAVIOR: 15,
    FlagType.ABNORMAL_GROWTH: 10,
    FlagType.REFERRAL_SELF_CHAIN: 30,
    FlagType.MULTIPLE_IPS: 20,
    FlagType.EARLY_WITHDRAWAL: 25,
}


def _get_severity(weight: int) -> FlagSeverity:
    if weight >= 25:
        return FlagSeverity.HIGH
    elif weight >= 20:
        return FlagSeverity.MEDIUM
    else:
        return FlagSeverity.LOW


class FraudService:

    @staticmethod
    async def check_rapid_completion(
        session: AsyncSession,
        user_id: int,
        window_seconds: int = 60,
        threshold: int = 5,
    ) -> Optional[FraudFlag]:
        """Flag if user completes >threshold tasks within window_seconds."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=window_seconds)
        result = await session.execute(
            select(sa_func.count(TaskCompletion.id))
            .where(
                TaskCompletion.user_id == user_id,
                TaskCompletion.verified_at >= cutoff,
            )
        )
        count = result.scalar() or 0

        if count >= threshold:
            return await FraudService._create_flag(
                session=session,
                user_id=user_id,
                flag_type=FlagType.RAPID_COMPLETION,
                details={
                    "completions_in_window": count,
                    "window_seconds": window_seconds,
                    "threshold": threshold,
                },
            )
        return None

    @staticmethod
    async def check_duplicate_wallet(
        session: AsyncSession,
        user_id: int,
        wallet_address: str,
    ) -> Optional[FraudFlag]:
        """Flag if wallet address is used by another account."""
        result = await session.execute(
            select(Wallet).where(
                Wallet.address == wallet_address.lower(),
                Wallet.user_id != user_id,
                Wallet.is_active == True,
            )
        )
        other_wallet = result.scalar_one_or_none()

        if other_wallet:
            return await FraudService._create_flag(
                session=session,
                user_id=user_id,
                flag_type=FlagType.DUPLICATE_WALLET,
                details={
                    "wallet": wallet_address,
                    "other_user_id": other_wallet.user_id,
                },
            )
        return None

    @staticmethod
    async def check_early_withdrawal(
        session: AsyncSession,
        user_id: int,
    ) -> Optional[FraudFlag]:
        """Flag withdrawal request within 1 hour of account creation."""
        user = await session.get(User, user_id)
        if not user:
            return None

        age = datetime.now(tz=timezone.utc) - user.joined_at
        if age < timedelta(hours=1):
            return await FraudService._create_flag(
                session=session,
                user_id=user_id,
                flag_type=FlagType.EARLY_WITHDRAWAL,
                details={"account_age_seconds": int(age.total_seconds())},
            )
        return None

    @staticmethod
    async def check_suspicious_referral_rate(
        session: AsyncSession,
        user_id: int,
        window_hours: int = 24,
        threshold: int = 10,
    ) -> Optional[FraudFlag]:
        """Flag if user referred >threshold people from same context."""
        from models.referral import Referral
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)
        result = await session.execute(
            select(sa_func.count(Referral.id)).where(
                Referral.referrer_id == user_id,
                Referral.created_at >= cutoff,
            )
        )
        count = result.scalar() or 0

        if count > threshold:
            return await FraudService._create_flag(
                session=session,
                user_id=user_id,
                flag_type=FlagType.SUSPICIOUS_REFERRAL,
                details={
                    "referrals_in_window": count,
                    "window_hours": window_hours,
                    "threshold": threshold,
                },
            )
        return None

    @staticmethod
    async def recalculate_fraud_score(
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """Recalculate fraud score from all active flags. Returns new score."""
        result = await session.execute(
            select(FraudFlag).where(
                FraudFlag.user_id == user_id,
                FraudFlag.reviewed == False,
            )
        )
        flags = result.scalars().all()

        score = 0
        for flag in flags:
            score += SIGNAL_WEIGHTS.get(flag.flag_type, 10)

        score = min(score, 100)

        # Apply auto-actions
        user = await session.get(User, user_id)
        if user:
            old_score = user.fraud_score
            user.fraud_score = score

            if score >= settings.FRAUD_AUTO_BAN_SCORE and user.status != UserStatus.BANNED:
                user.status = UserStatus.BANNED
                log.warning(
                    "User auto-banned by fraud score",
                    user_id=user_id,
                    score=score,
                )
            elif score >= settings.FRAUD_RESTRICT_SCORE and user.status == UserStatus.ACTIVE:
                user.status = UserStatus.RESTRICTED
                log.warning(
                    "User auto-restricted by fraud score",
                    user_id=user_id,
                    score=score,
                )
            elif score >= settings.FRAUD_FLAG_SCORE and user.status == UserStatus.ACTIVE:
                user.status = UserStatus.FLAGGED

            await session.flush()

            if score != old_score:
                log.info(
                    "Fraud score updated",
                    user_id=user_id,
                    old_score=old_score,
                    new_score=score,
                )

        return score

    @staticmethod
    async def _create_flag(
        session: AsyncSession,
        user_id: int,
        flag_type: FlagType,
        details: Optional[dict] = None,
    ) -> FraudFlag:
        """Create a fraud flag and schedule score recalculation."""
        severity = _get_severity(SIGNAL_WEIGHTS.get(flag_type, 10))

        flag = FraudFlag(
            user_id=user_id,
            flag_type=flag_type,
            severity=severity,
            details=details or {},
        )
        session.add(flag)
        await session.flush()

        log.warning(
            "Fraud flag created",
            user_id=user_id,
            flag_type=flag_type,
            severity=severity,
        )

        # Notify admin of HIGH/CRITICAL flags
        if severity in (FlagSeverity.HIGH, FlagSeverity.CRITICAL):
            from services.notification_service import NotificationService
            # Async, non-blocking
            import asyncio
            asyncio.create_task(
                NotificationService.notify_admin_fraud(
                    user_id=user_id,
                    flag_type=flag_type,
                    severity=severity,
                    details=details or {},
                )
            )

        return flag
