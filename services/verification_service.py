"""
Verification Service — validates task completion eligibility and membership.
Never assumes membership; always calls Telegram API to verify.
"""
import enum
from dataclasses import dataclass
from datetime import timezone
from typing import Optional

import structlog
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.error import TelegramError, BadRequest

from models.campaign import Campaign, CampaignStatus
from models.task_completion import TaskCompletion
from models.task_skip import TaskSkip
from models.user import User, UserStatus

log = structlog.get_logger(__name__)

# Membership states that count as "joined"
VALID_MEMBERSHIP_STATES = {"member", "administrator", "creator"}


class FailureReason(str, enum.Enum):
    CAMPAIGN_NOT_FOUND = "CAMPAIGN_NOT_FOUND"
    CAMPAIGN_NOT_ACTIVE = "CAMPAIGN_NOT_ACTIVE"
    CAMPAIGN_EXPIRED = "CAMPAIGN_EXPIRED"
    CAMPAIGN_BUDGET_EXHAUSTED = "CAMPAIGN_BUDGET_EXHAUSTED"
    CAMPAIGN_LIMIT_REACHED = "CAMPAIGN_LIMIT_REACHED"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    TASK_SKIPPED = "TASK_SKIPPED"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_BANNED = "USER_BANNED"
    USER_RESTRICTED = "USER_RESTRICTED"
    NOT_MEMBER = "NOT_MEMBER"
    TELEGRAM_ERROR = "TELEGRAM_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass
class VerificationResult:
    success: bool
    reason: Optional[FailureReason] = None
    membership_status: Optional[str] = None
    campaign: Optional[Campaign] = None
    user: Optional[User] = None
    error_message: Optional[str] = None


class VerificationService:

    @staticmethod
    async def verify_task_completion(
        bot: Bot,
        session: AsyncSession,
        user_id: int,
        campaign_id: int,
    ) -> VerificationResult:
        """
        Full pre-reward verification pipeline.
        Returns a VerificationResult — caller must not award reward on failure.
        """
        from datetime import datetime

        # 1. Load campaign
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            return VerificationResult(
                success=False,
                reason=FailureReason.CAMPAIGN_NOT_FOUND,
                error_message=f"Campaign {campaign_id} not found",
            )

        # 2. Status check
        if campaign.status != CampaignStatus.ACTIVE:
            return VerificationResult(
                success=False,
                reason=FailureReason.CAMPAIGN_NOT_ACTIVE,
                campaign=campaign,
                error_message=f"Campaign is {campaign.status}",
            )

        # 3. Expiry check
        now = datetime.now(tz=timezone.utc)
        if campaign.expires_at and now > campaign.expires_at:
            return VerificationResult(
                success=False,
                reason=FailureReason.CAMPAIGN_EXPIRED,
                campaign=campaign,
                error_message="Campaign has expired",
            )

        # 4. Budget check
        if campaign.spent_budget >= campaign.total_budget:
            return VerificationResult(
                success=False,
                reason=FailureReason.CAMPAIGN_BUDGET_EXHAUSTED,
                campaign=campaign,
                error_message="Campaign budget exhausted",
            )

        # 5. Completion limit check
        if campaign.completed_count >= campaign.completion_limit:
            return VerificationResult(
                success=False,
                reason=FailureReason.CAMPAIGN_LIMIT_REACHED,
                campaign=campaign,
                error_message="Campaign completion limit reached",
            )

        # 6. Already completed?
        existing_completion = await session.execute(
            select(TaskCompletion).where(
                TaskCompletion.user_id == user_id,
                TaskCompletion.campaign_id == campaign_id,
            )
        )
        if existing_completion.scalar_one_or_none():
            return VerificationResult(
                success=False,
                reason=FailureReason.ALREADY_COMPLETED,
                campaign=campaign,
                error_message="User already completed this task",
            )

        # 7. Skipped?
        existing_skip = await session.execute(
            select(TaskSkip).where(
                TaskSkip.user_id == user_id,
                TaskSkip.campaign_id == campaign_id,
            )
        )
        if existing_skip.scalar_one_or_none():
            return VerificationResult(
                success=False,
                reason=FailureReason.TASK_SKIPPED,
                campaign=campaign,
                error_message="User skipped this task",
            )

        # 8. Load user
        user = await session.get(User, user_id)
        if not user:
            return VerificationResult(
                success=False,
                reason=FailureReason.USER_NOT_FOUND,
                campaign=campaign,
                error_message=f"User {user_id} not found",
            )

        # 9. User status check
        if user.status == UserStatus.BANNED:
            return VerificationResult(
                success=False,
                reason=FailureReason.USER_BANNED,
                campaign=campaign,
                user=user,
                error_message="User is banned",
            )
        if user.status == UserStatus.RESTRICTED:
            return VerificationResult(
                success=False,
                reason=FailureReason.USER_RESTRICTED,
                campaign=campaign,
                user=user,
                error_message="User is restricted",
            )

        # 10. Telegram membership verification
        from models.campaign import TaskType
        if campaign.task_type in (
            TaskType.CHANNEL_JOIN,
            TaskType.GROUP_JOIN,
            TaskType.CHANNEL_GROUP_JOIN,
            TaskType.FORCE_JOIN,
        ):
            membership_result = await VerificationService._verify_membership(
                bot=bot,
                user_id=user_id,
                chat_id=campaign.telegram_chat_id,
            )
            if not membership_result["success"]:
                return VerificationResult(
                    success=False,
                    reason=FailureReason.NOT_MEMBER,
                    campaign=campaign,
                    user=user,
                    error_message=membership_result.get("error", "Not a member"),
                )
            membership_status = membership_result["membership_status"]
        else:
            membership_status = "verified"

        return VerificationResult(
            success=True,
            membership_status=membership_status,
            campaign=campaign,
            user=user,
        )

    @staticmethod
    async def _verify_membership(
        bot: Bot,
        user_id: int,
        chat_id: int,
    ) -> dict:
        """Call Telegram API to check if user is a member of the chat."""
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            status = member.status  # member, administrator, creator, left, kicked, restricted

            if status in VALID_MEMBERSHIP_STATES:
                return {
                    "success": True,
                    "membership_status": status,
                }
            else:
                log.info(
                    "User not a valid member",
                    user_id=user_id,
                    chat_id=chat_id,
                    status=status,
                )
                return {
                    "success": False,
                    "membership_status": status,
                    "error": f"Membership status '{status}' is not sufficient",
                }
        except BadRequest as e:
            log.warning(
                "BadRequest checking membership",
                user_id=user_id,
                chat_id=chat_id,
                error=str(e),
            )
            return {"success": False, "error": str(e)}
        except TelegramError as e:
            log.error(
                "Telegram API error during membership check",
                user_id=user_id,
                chat_id=chat_id,
                error=str(e),
            )
            return {"success": False, "error": str(e)}
