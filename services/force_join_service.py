"""
Force Join Service — enforce mandatory channel membership before bot access.
"""
from typing import List, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from models.force_join import ForceJoinChannel

log = structlog.get_logger(__name__)


class ForceJoinService:

    @staticmethod
    async def get_active_channels(session: AsyncSession) -> List[ForceJoinChannel]:
        """Get all active force-join channels."""
        result = await session.execute(
            select(ForceJoinChannel).where(ForceJoinChannel.is_active == True)
        )
        return list(result.scalars().all())

    @staticmethod
    async def check_user_membership(
        bot: Bot,
        session: AsyncSession,
        user_id: int,
    ) -> Tuple[bool, List[ForceJoinChannel]]:
        """
        Check if user is member of all force-join channels.
        Returns (all_joined, list_of_missing_channels).
        """
        channels = await ForceJoinService.get_active_channels(session)
        missing = []

        for channel in channels:
            try:
                member = await bot.get_chat_member(
                    chat_id=channel.chat_id, user_id=user_id
                )
                if member.status not in ("member", "administrator", "creator"):
                    missing.append(channel)
            except TelegramError as e:
                log.warning(
                    "Could not check force-join membership",
                    channel_id=channel.chat_id,
                    user_id=user_id,
                    error=str(e),
                )
                # On error, don't block user
                continue

        return len(missing) == 0, missing

    @staticmethod
    def build_join_keyboard(missing_channels: List[ForceJoinChannel]) -> InlineKeyboardMarkup:
        """Build inline keyboard with join buttons for each missing channel."""
        buttons = []
        for ch in missing_channels:
            if ch.invite_url:
                url = ch.invite_url
            elif ch.username:
                url = f"https://t.me/{ch.username.lstrip('@')}"
            else:
                continue
            buttons.append([InlineKeyboardButton(
                f"📢 Join Channel", url=url
            )])
        buttons.append([InlineKeyboardButton(
            "✅ I've Joined — Check Again",
            callback_data="force_join_check"
        )])
        return InlineKeyboardMarkup(buttons)
