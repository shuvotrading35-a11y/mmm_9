"""
Campaign Service — campaign lifecycle, funding, and analytics.
"""
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List

import structlog
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.campaign import Campaign, CampaignStatus, TaskType
from models.sponsor import Sponsor, SponsorStatus
from models.transaction import TransactionType
from services.ledger_service import LedgerService, InsufficientFundsError

log = structlog.get_logger(__name__)


def _enum_str(v) -> str:
    """Convert enum or str to string safely."""
    if v is None:
        return ""
    return v.value if hasattr(v, "value") else str(v)


class CampaignValidationError(Exception):
    pass


class CampaignService:

    @staticmethod
    async def create_campaign(
        session: AsyncSession,
        sponsor_id: int,
        title: str,
        description: Optional[str],
        task_type: TaskType,
        telegram_chat_id: Optional[int],
        telegram_username: Optional[str],
        invite_url: Optional[str],
        reward_per_user: Decimal,
        completion_limit: int,
        duration_days: int,
    ) -> Campaign:
        """Create a new campaign in PENDING status (awaiting admin approval)."""
        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            raise CampaignValidationError("Sponsor not found")
        if sponsor.status != SponsorStatus.APPROVED:
            raise CampaignValidationError("Sponsor account not approved")

        if reward_per_user < settings.TASK_MIN_REWARD:
            raise CampaignValidationError(
                f"Reward must be at least {settings.TASK_MIN_REWARD} USDT"
            )
        if reward_per_user > settings.TASK_MAX_REWARD:
            raise CampaignValidationError(
                f"Reward must not exceed {settings.TASK_MAX_REWARD} USDT"
            )

        total_budget = reward_per_user * completion_limit
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=duration_days)

        campaign = Campaign(
            sponsor_id=sponsor_id,
            title=title,
            description=description,
            task_type=task_type,
            telegram_chat_id=telegram_chat_id,
            telegram_username=telegram_username,
            invite_url=invite_url,
            reward_per_user=reward_per_user,
            completion_limit=completion_limit,
            total_budget=total_budget,
            reserved_budget=Decimal("0"),
            spent_budget=Decimal("0"),
            status=CampaignStatus.PENDING,
            expires_at=expires_at,
        )
        session.add(campaign)
        await session.flush()

        log.info(
            "Campaign created",
            campaign_id=campaign.id,
            sponsor_id=sponsor_id,
            budget=str(total_budget),
        )

        # Notify admins (fire-and-forget)
        from services.notification_service import NotificationService
        asyncio.create_task(
            NotificationService.notify_admin_new_campaign(
                campaign.id, title, sponsor_id
            )
        )

        return campaign

    @staticmethod
    async def approve_campaign(
        session: AsyncSession,
        campaign_id: int,
        admin_id: int,
    ) -> Campaign:
        """Admin approves a PENDING campaign → PENDING_FUNDING."""
        result = await session.execute(
            select(Campaign)
            .options(selectinload(Campaign.sponsor))
            .where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise CampaignValidationError("Campaign not found")
        if campaign.status != CampaignStatus.PENDING:
            raise CampaignValidationError(
                f"Campaign is {campaign.status}, cannot approve"
            )

        campaign.status = CampaignStatus.PENDING_FUNDING
        campaign.approved_by = admin_id
        campaign.approved_at = datetime.now(tz=timezone.utc)

        # Snapshot inside session
        sponsor_user_id = campaign.sponsor.user_id
        campaign_title = campaign.title
        campaign_id_val = campaign.id

        await session.flush()

        # Notify sponsor (fire-and-forget)
        from services.notification_service import NotificationService
        asyncio.create_task(
            NotificationService.campaign_approved(sponsor_user_id, campaign_title)
        )

        log.info(
            "Campaign approved",
            campaign_id=campaign_id_val,
            admin_id=admin_id,
        )

        return campaign

    @staticmethod
    async def fund_campaign(
        session: AsyncSession,
        campaign_id: int,
        sponsor_id: int,
    ) -> Campaign:
        """
        Sponsor funds campaign from available_balance.
        Moves funds to reserved_balance and sets campaign ACTIVE.
        """
        result = await session.execute(
            select(Campaign)
            .options(selectinload(Campaign.sponsor))     # ← for notify
            .where(Campaign.id == campaign_id)
            .with_for_update(nowait=True)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise CampaignValidationError("Campaign not found")
        if campaign.sponsor_id != sponsor_id:
            raise CampaignValidationError("Not your campaign")
        if campaign.status != CampaignStatus.PENDING_FUNDING:
            raise CampaignValidationError(
                f"Campaign cannot be funded in status {campaign.status}"
            )

        required = campaign.total_budget
        idem_key = hashlib.sha256(
            f"fund_campaign:{campaign_id}:{settings.SECRET_SALT}".encode()
        ).hexdigest()

        try:
            await LedgerService.debit_sponsor_for_campaign(
                session=session,
                sponsor_id=sponsor_id,
                amount=required,
                campaign_id=campaign_id,
                idempotency_key=idem_key,
            )
        except InsufficientFundsError:
            raise CampaignValidationError(
                f"Insufficient balance. Required: {required} USDT. "
                f"Please deposit more funds first."
            )

        campaign.reserved_budget = required
        campaign.status = CampaignStatus.ACTIVE

        # Snapshot inside session
        sponsor_user_id = campaign.sponsor.user_id
        campaign_title = campaign.title

        await session.flush()

        # Notify sponsor (fire-and-forget)
        from services.notification_service import NotificationService
        asyncio.create_task(
            NotificationService.campaign_funded(
                sponsor_user_id, campaign_title, str(required)
            )
        )

        log.info(
            "Campaign funded and activated",
            campaign_id=campaign_id,
            budget=str(required),
        )
        return campaign

    @staticmethod
    async def pause_campaign(
        session: AsyncSession,
        campaign_id: int,
        actor_id: int,
    ) -> Campaign:
        """Pause an active campaign (sponsor or admin)."""
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            raise CampaignValidationError("Campaign not found")
        if campaign.status != CampaignStatus.ACTIVE:
            raise CampaignValidationError("Can only pause ACTIVE campaigns")

        campaign.status = CampaignStatus.PAUSED
        await session.flush()
        return campaign

    @staticmethod
    async def resume_campaign(
        session: AsyncSession,
        campaign_id: int,
    ) -> Campaign:
        """Resume a paused campaign."""
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            raise CampaignValidationError("Campaign not found")
        if campaign.status != CampaignStatus.PAUSED:
            raise CampaignValidationError("Campaign is not paused")
        campaign.status = CampaignStatus.ACTIVE
        await session.flush()
        return campaign

    @staticmethod
    async def expire_overdue_campaigns(session: AsyncSession) -> int:
        """
        Background job: expire campaigns past their expiry date.
        Releases unused budget back to sponsor and notifies them.
        """
        now = datetime.now(tz=timezone.utc)

        # Eager-load sponsor so we can notify without lazy loads
        result = await session.execute(
            select(Campaign)
            .options(selectinload(Campaign.sponsor))
            .where(
                Campaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.PAUSED]),
                Campaign.expires_at < now,
            )
        )
        campaigns = result.scalars().all()
        expired_count = 0

        for campaign in campaigns:
            release_key = hashlib.sha256(
                f"expire_release:{campaign.id}:{settings.SECRET_SALT}".encode()
            ).hexdigest()

            unused = campaign.reserved_budget or Decimal("0")
            released = Decimal("0")

            if unused > Decimal("0"):
                try:
                    await LedgerService.release_campaign_budget(
                        session=session,
                        sponsor_id=campaign.sponsor_id,
                        amount=unused,
                        campaign_id=campaign.id,
                        idempotency_key=release_key,
                        description=f"Budget release: expired campaign #{campaign.id}",
                    )
                    released = unused
                except Exception as e:
                    log.error(
                        "Failed to release expired campaign budget",
                        campaign_id=campaign.id,
                        error=str(e),
                    )

            # Snapshot before mutating
            sponsor_user_id = campaign.sponsor.user_id
            campaign_title = campaign.title
            campaign_id_val = campaign.id

            campaign.status = CampaignStatus.EXPIRED
            campaign.reserved_budget = Decimal("0")
            expired_count += 1

            log.info("Campaign expired", campaign_id=campaign_id_val)

            # Notify sponsor (fire-and-forget)
            from services.notification_service import NotificationService
            asyncio.create_task(
                NotificationService.campaign_expired(
                    sponsor_user_id, campaign_title, str(released)
                )
            )

        await session.flush()
        return expired_count

    @staticmethod
    async def get_sponsor_campaigns(
        session: AsyncSession,
        sponsor_id: int,
    ) -> List[Campaign]:
        result = await session.execute(
            select(Campaign)
            .where(Campaign.sponsor_id == sponsor_id)
            .order_by(Campaign.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_campaign_analytics(
        session: AsyncSession,
        campaign_id: int,
    ) -> dict:
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            return {}

        completion_rate = (
            (campaign.completed_count / campaign.view_count * 100)
            if campaign.view_count > 0 else 0
        )

        return {
            "id": campaign.id,
            "title": campaign.title,
            "status": _enum_str(campaign.status),
            "view_count": campaign.view_count,
            "click_count": campaign.click_count,
            "completed_count": campaign.completed_count,
            "failed_verify_count": campaign.failed_verify_count,
            "skip_count": campaign.skip_count,
            "completion_rate": round(completion_rate, 1),
            "total_budget": campaign.total_budget,
            "spent_budget": campaign.spent_budget,
            "remaining_budget": campaign.remaining_budget,
            "expires_at": campaign.expires_at,
        }

    @staticmethod
    async def delete_campaign(
        session: AsyncSession,
        campaign_id: int,
        actor_id: int,
        actor_is_admin: bool = False,
    ) -> dict:
        """
        Delete a campaign. If it has reserved budget, release it back to the sponsor.
        Returns a summary dict with 'released' amount.
        """
        from models.task_completion import TaskCompletion
        from models.task_skip import TaskSkip

        # Eager-load sponsor to fetch user_id for notifications
        result = await session.execute(
            select(Campaign)
            .options(selectinload(Campaign.sponsor))
            .where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise CampaignValidationError("Campaign not found")

        status_str = _enum_str(campaign.status)

        # Business rules
        if status_str == "COMPLETED":
            raise CampaignValidationError("Completed campaigns cannot be deleted")

        # Sponsors can only delete their own campaigns
        if not actor_is_admin:
            sponsor = await session.get(Sponsor, campaign.sponsor_id)
            if not sponsor or sponsor.id != actor_id:
                raise CampaignValidationError("Not your campaign")

        reserved = campaign.reserved_budget or Decimal("0")
        released = Decimal("0")

        # Release reserved budget back to sponsor
        if reserved > Decimal("0"):
            release_key = hashlib.sha256(
                f"delete_release:{campaign_id}:{settings.SECRET_SALT}".encode()
            ).hexdigest()
            try:
                await LedgerService.release_campaign_budget(
                    session=session,
                    sponsor_id=campaign.sponsor_id,
                    amount=reserved,
                    campaign_id=campaign_id,
                    idempotency_key=release_key,
                    description=f"Budget release: deleted campaign #{campaign_id}",
                )
                released = reserved
            except Exception as e:
                log.error(
                    "Failed to release budget on delete",
                    campaign_id=campaign_id,
                    error=str(e),
                )

        # Snapshot before deletion
        summary = {
            "id": campaign.id,
            "title": campaign.title,
            "sponsor_id": campaign.sponsor_id,
            "sponsor_user_id": campaign.sponsor.user_id,
            "status": status_str,
            "released": released,
        }

        # Delete related rows to avoid FK violations
        await session.execute(
            sa_delete(TaskCompletion).where(TaskCompletion.campaign_id == campaign_id)
        )
        await session.execute(
            sa_delete(TaskSkip).where(TaskSkip.campaign_id == campaign_id)
        )

        await session.delete(campaign)
        await session.flush()

        log.info(
            "Campaign deleted",
            campaign_id=campaign_id,
            actor_id=actor_id,
            admin=actor_is_admin,
            released=str(released),
        )

        # Notify sponsor if an admin deleted their campaign
        if actor_is_admin:
            from services.notification_service import NotificationService
            asyncio.create_task(
                NotificationService.send_to_user(
                    summary["sponsor_user_id"],
                    f"🗑 <b>Campaign Deleted by Admin</b>\n\n"
                    f"📝 <b>{summary['title']}</b>\n"
                    + (
                        f"💰 Refunded to your balance: <b>{released} USDT</b>"
                        if released > Decimal("0") else ""
                    ),
                )
            )

        return summary