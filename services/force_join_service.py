"""
Force Join Service — enforce mandatory channel membership before bot access.
"""
import asyncio
from typing import List, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from models.force_join import ForceJoinChannel

log = structlog.get_logger(__name__)


class ForceJoinService:

    # In-memory dedupe: user_id → last notified timestamp (seconds)
    # Prevents spamming the same user every job run.
    _last_notified: dict = {}

    # ══════════════════════════════════════════════════════════════
    # Core membership checks (used by middleware + button handler)
    # ══════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════
    # Periodic background check (APScheduler job)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    async def run_periodic_check(bot: Bot, batch_size: int = 100) -> dict:
        """
        Background job: scan all active users, verify force-join membership,
        and notify those who have left any required channel.

        Called from bot.py on a schedule (e.g. every 6 hours).
        Returns a summary dict.
        """
        import time
        from database import get_session
        from models.user import User, UserStatus

        started = time.time()
        checked = 0
        missing_count = 0
        notified = 0
        errors = 0

        # 1. Load active channels
        async with get_session() as session:
            ch_result = await session.execute(
                select(ForceJoinChannel).where(ForceJoinChannel.is_active == True)
            )
            channels = list(ch_result.scalars().all())

        if not channels:
            log.info("Force-join periodic check: no active channels, skipping")
            return {"checked": 0, "missing": 0, "notified": 0, "errors": 0}

        # 2. Load all non-banned user IDs
        async with get_session() as session:
            u_result = await session.execute(
                select(User.id).where(User.status != UserStatus.BANNED)
            )
            user_ids = [row[0] for row in u_result.all()]

        # 3. Check each user against each channel
        for user_id in user_ids:
            checked += 1

            missing_channels = []
            for ch in channels:
                try:
                    member = await bot.get_chat_member(
                        chat_id=ch.chat_id, user_id=user_id
                    )
                    if member.status not in ("member", "administrator", "creator"):
                        missing_channels.append(ch)
                except TelegramError as e:
                    errors += 1
                    log.debug(
                        "get_chat_member failed in periodic check",
                        user_id=user_id,
                        chat_id=ch.chat_id,
                        error=str(e),
                    )
                    # On error, don't block — continue
                    continue

            if not missing_channels:
                continue

            missing_count += 1

            # Dedupe — only notify once per 6 hours per user
            now = time.time()
            last = ForceJoinService._last_notified.get(user_id, 0)
            if now - last < 6 * 3600:
                continue

            # Send combined notice
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=ForceJoinService._build_violation_message(missing_channels),
                    parse_mode="HTML",
                    reply_markup=ForceJoinService._build_violation_keyboard(missing_channels),
                )
                ForceJoinService._last_notified[user_id] = now
                notified += 1
            except Exception as e:
                # User blocked the bot, or other send error
                log.debug(
                    "Could not send force-join warning",
                    user_id=user_id,
                    error=str(e),
                )

            # Gentle rate limit — avoid Telegram 429
            await asyncio.sleep(0.05)

        elapsed = time.time() - started
        summary = {
            "checked": checked,
            "missing": missing_count,
            "notified": notified,
            "errors": errors,
            "elapsed_s": round(elapsed, 1),
        }
        log.info("Force-join periodic check complete", **summary)
        return summary

    # ── Helpers for periodic check ───────────────────────────────

    @staticmethod
    def _build_violation_message(missing_channels: List[ForceJoinChannel]) -> str:
        """Human-readable HTML message listing all missing channels."""
        names = []
        for ch in missing_channels:
            if ch.username:
                names.append(f"@{ch.username}")
            elif getattr(ch, "title", None):
                names.append(ch.title)
            else:
                names.append(str(ch.chat_id))

        joined = "\n".join(f"• <b>{n}</b>" for n in names)

        return (
            f"⚠️ <b>Channel Membership Required</b>\n\n"
            f"We noticed you have left one or more required channels:\n\n"
            f"{joined}\n\n"
            f"Please re-join to continue using this bot. "
            f"Tap the button(s) below to join, then press ✅ Check."
        )

    @staticmethod
    def _build_violation_keyboard(
        missing_channels: List[ForceJoinChannel],
    ) -> InlineKeyboardMarkup:
        """Re-join buttons for all missing channels, plus a check button."""
        buttons = []
        for ch in missing_channels:
            url = None
            if ch.invite_url:
                url = ch.invite_url
            elif ch.username:
                url = f"https://t.me/{ch.username.lstrip('@')}"
            if not url:
                continue
            label = f"📢 Join @{ch.username}" if ch.username else "📢 Join Channel"
            buttons.append([InlineKeyboardButton(label[:50], url=url)])

        buttons.append([InlineKeyboardButton(
            "✅ I've Joined — Check Again",
            callback_data="force_join_check",
        )])
        return InlineKeyboardMarkup(buttons)