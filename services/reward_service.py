"""
Reward Service — atomic task reward execution.
Single database transaction: campaign debit + user credit + completion record.
"""
import hashlib
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.campaign import Campaign, CampaignStatus
from models.task_completion import TaskCompletion
from models.transaction import TransactionType
from models.user import User
from services.ledger_service import LedgerService, IdempotencyConflictError
from services.verification_service import VerificationResult

log = structlog.get_logger(__name__)


def _make_reward_idempotency_key(user_id: int, campaign_id: int) -> str:
    """Deterministic idempotency key for task rewards."""
    from config import settings
    raw = f"reward:{user_id}:{campaign_id}:{settings.SECRET_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _make_commission_idempotency_key(
    referrer_id: int, referred_id: int, campaign_id: int
) -> str:
    from config import settings
    raw = f"commission:{referrer_id}:{referred_id}:{campaign_id}:{settings.SECRET_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


class RewardService:

    @staticmethod
    async def execute_reward(
        session: AsyncSession,
        user_id: int,
        campaign_id: int,
        verification_result: VerificationResult,
    ) -> TaskCompletion:
        """
        Execute task reward atomically. Must be called within session.begin().

        Steps:
        1. Re-lock campaign and user rows
        2. Re-verify conditions (double-check after locks)
        3. Check idempotency
        4. Debit campaign budget
        5. Credit user balance
        6. Insert task_completion
        7. Update counters
        """
        reward_key = _make_reward_idempotency_key(user_id, campaign_id)

        # Re-lock campaign
        result = await session.execute(
            select(Campaign)
            .where(Campaign.id == campaign_id)
            .with_for_update(nowait=True)
        )
        campaign = result.scalar_one_or_none()
        if not campaign or campaign.status != CampaignStatus.ACTIVE:
            raise ValueError(f"Campaign {campaign_id} no longer active")

        # Re-verify budget and limit (post-lock)
        if campaign.spent_budget >= campaign.total_budget:
            raise ValueError("Campaign budget exhausted after lock")
        if campaign.completed_count >= campaign.completion_limit:
            raise ValueError("Campaign limit reached after lock")

        # Re-lock user
        result = await session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update(nowait=True)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found after lock")

        reward_amount = campaign.reward_per_user

        # Debit campaign budget
        campaign.spent_budget += reward_amount
        campaign.reserved_budget -= reward_amount
        campaign.completed_count += 1

        # Auto-complete campaign if limits hit
        if (campaign.completed_count >= campaign.completion_limit or
                campaign.spent_budget >= campaign.total_budget):
            campaign.status = CampaignStatus.COMPLETED
            log.info("Campaign auto-completed", campaign_id=campaign_id)

        # Credit user
        try:
            tx = await LedgerService.credit_user(
                session=session,
                user_id=user_id,
                amount=reward_amount,
                tx_type=TransactionType.TASK_REWARD,
                reference_id=campaign_id,
                reference_type="campaign",
                idempotency_key=reward_key,
                description=f"Task reward: {campaign.title}",
                update_total_earned=True,
            )
        except IdempotencyConflictError:
            # Task was already rewarded — find the existing completion
            existing = await session.execute(
                select(TaskCompletion).where(
                    TaskCompletion.idempotency_key == reward_key
                )
            )
            return existing.scalar_one()

        # Record completion
        completion = TaskCompletion(
            user_id=user_id,
            campaign_id=campaign_id,
            reward_amount=reward_amount,
            membership_status=verification_result.membership_status,
            idempotency_key=reward_key,
        )
        session.add(completion)
        user.tasks_completed += 1

        await session.flush()

        log.info(
            "Task reward executed",
            user_id=user_id,
            campaign_id=campaign_id,
            reward=str(reward_amount),
            tx_id=tx.id,
        )

        return completion

    @staticmethod
    async def pay_referral_commission(
        session: AsyncSession,
        referred_user_id: int,
        campaign_id: int,
        task_reward_amount: Decimal,
    ) -> Optional[int]:
        """
        Pay referral commission to the referrer.
        This is a separate, non-blocking operation.
        Returns commission transaction ID or None.
        """
        from config import settings
        from models.referral import Referral

        # Load referral record
        result = await session.execute(
            select(Referral).where(Referral.referred_id == referred_user_id)
        )
        referral = result.scalar_one_or_none()
        if not referral:
            return None

        referrer_id = referral.referrer_id
        commission_pct = settings.REFERRAL_COMMISSION_PCT / Decimal("100")
        commission_amount = (task_reward_amount * commission_pct).quantize(Decimal("0.00000001"))

        if commission_amount <= Decimal("0"):
            return None

        commission_key = _make_commission_idempotency_key(
            referrer_id, referred_user_id, campaign_id
        )

        try:
            tx = await LedgerService.credit_user(
                session=session,
                user_id=referrer_id,
                amount=commission_amount,
                tx_type=TransactionType.REFERRAL_COMMISSION,
                reference_id=campaign_id,
                reference_type="campaign",
                idempotency_key=commission_key,
                description=f"Commission from referral task completion #{campaign_id}",
                update_total_earned=True,
            )
            # Update referral stats
            referral.commission_earned += commission_amount
            await session.flush()

            log.info(
                "Referral commission paid",
                referrer_id=referrer_id,
                referred_id=referred_user_id,
                commission=str(commission_amount),
            )
            return tx.id

        except IdempotencyConflictError:
            log.info("Commission already paid", key=commission_key)
            return None
        except Exception as e:
            log.error("Commission payment failed", error=str(e))
            # Commission failure must not block task reward
            return None

    @staticmethod
    async def pay_referral_signup_reward(
        session: AsyncSession,
        referrer_id: int,
        referred_user_id: int,
    ) -> Optional[int]:
        """Pay one-time referral signup reward to the referrer."""
        import hashlib
        from config import settings
        from models.referral import Referral

        key_raw = f"ref_reward:{referrer_id}:{referred_user_id}:{settings.SECRET_SALT}"
        idempotency_key = hashlib.sha256(key_raw.encode()).hexdigest()

        reward_amount = settings.REFERRAL_REWARD

        try:
            tx = await LedgerService.credit_user(
                session=session,
                user_id=referrer_id,
                amount=reward_amount,
                tx_type=TransactionType.REFERRAL_REWARD,
                reference_id=referred_user_id,
                reference_type="user",
                idempotency_key=idempotency_key,
                description=f"Referral reward: new user {referred_user_id}",
                update_total_earned=True,
            )

            # Update referral record
            result = await session.execute(
                select(Referral).where(Referral.referred_id == referred_user_id)
            )
            referral = result.scalar_one_or_none()
            if referral:
                referral.reward_paid = reward_amount

            await session.flush()

            log.info(
                "Referral signup reward paid",
                referrer_id=referrer_id,
                referred_id=referred_user_id,
                reward=str(reward_amount),
            )
            return tx.id

        except IdempotencyConflictError:
            log.info("Referral reward already paid", referrer_id=referrer_id)
            return None
