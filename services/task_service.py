"""
Task Service — task browsing, serving, and lifecycle management.
"""
from typing import Optional, List, Tuple

import structlog
from sqlalchemy import select, and_, not_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from models.campaign import Campaign, CampaignStatus
from models.task_completion import TaskCompletion
from models.task_skip import TaskSkip
from models.user import User

log = structlog.get_logger(__name__)


class TaskService:

    @staticmethod
    async def get_next_task(
        session: AsyncSession,
        user_id: int,
    ) -> Optional[Campaign]:
        """
        Get the next available task for a user.
        Excludes: completed tasks, skipped tasks, inactive campaigns.
        Returns None if no tasks available.
        """
        # Subquery: campaigns already completed by user
        completed_subq = select(TaskCompletion.campaign_id).where(
            TaskCompletion.user_id == user_id
        )
        # Subquery: campaigns skipped by user
        skipped_subq = select(TaskSkip.campaign_id).where(
            TaskSkip.user_id == user_id
        )

        result = await session.execute(
            select(Campaign)
            .where(
                Campaign.status == CampaignStatus.ACTIVE,
                not_(Campaign.id.in_(completed_subq)),
                not_(Campaign.id.in_(skipped_subq)),
                Campaign.completed_count < Campaign.completion_limit,
                Campaign.spent_budget < Campaign.total_budget,
            )
            .order_by(Campaign.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_available_tasks_count(
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """Count tasks available for a specific user."""
        completed_subq = select(TaskCompletion.campaign_id).where(
            TaskCompletion.user_id == user_id
        )
        skipped_subq = select(TaskSkip.campaign_id).where(
            TaskSkip.user_id == user_id
        )

        result = await session.execute(
            select(Campaign)
            .where(
                Campaign.status == CampaignStatus.ACTIVE,
                not_(Campaign.id.in_(completed_subq)),
                not_(Campaign.id.in_(skipped_subq)),
                Campaign.completed_count < Campaign.completion_limit,
                Campaign.spent_budget < Campaign.total_budget,
            )
        )
        return len(result.scalars().all())

    @staticmethod
    async def record_view(session: AsyncSession, campaign_id: int) -> None:
        """Increment view count for analytics."""
        campaign = await session.get(Campaign, campaign_id)
        if campaign:
            campaign.view_count += 1
            await session.flush()

    @staticmethod
    async def record_click(session: AsyncSession, campaign_id: int) -> None:
        """Increment click count when user clicks 'Join'."""
        campaign = await session.get(Campaign, campaign_id)
        if campaign:
            campaign.click_count += 1
            await session.flush()

    @staticmethod
    async def record_failed_verify(session: AsyncSession, campaign_id: int) -> None:
        """Increment failed verification count."""
        campaign = await session.get(Campaign, campaign_id)
        if campaign:
            campaign.failed_verify_count += 1
            await session.flush()

    @staticmethod
    async def record_skip(
        session: AsyncSession,
        user_id: int,
        campaign_id: int,
    ) -> TaskSkip:
        """Record that a user skipped a task."""
        skip = TaskSkip(user_id=user_id, campaign_id=campaign_id)
        session.add(skip)

        # Update user skip counter
        user = await session.get(User, user_id)
        if user:
            user.tasks_skipped += 1

        # Update campaign skip count
        campaign = await session.get(Campaign, campaign_id)
        if campaign:
            campaign.skip_count += 1

        await session.flush()
        return skip

    @staticmethod
    async def get_active_campaigns(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Campaign]:
        """Get all active campaigns (for admin view)."""
        result = await session.execute(
            select(Campaign)
            .where(Campaign.status == CampaignStatus.ACTIVE)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
