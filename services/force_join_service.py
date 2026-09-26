"""
Force Join Service — enforce mandatory channel membership before bot access.
"""
import asyncio
import time
from typing import List, Tuple, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram._utils.types import JSONDict
from telegram.error import TelegramError

from models.force_join import ForceJoinChannel

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Styled button
# ══════════════════════════════════════════════════════════════════
# NOTE: move to keyboards/style.py and import everywhere.

class StyledButton(InlineKeyboardButton):
    """InlineKeyboardButton with an optional `style` field."""

    __slots__ = ("_style",)

    def __init__(self, text: str, style: Optional[str] = None, **kwargs):
        super().__init__(text=text, **kwargs)
        object.__setattr__(self, "_style", style)

    def to_dict(self, recursive: bool = True) -> JSONDict:
        data = super().to_dict(recursive=recursive)
        if self._style:
            data["style"] = self._style
        return data


def _resolve_join_url(ch: ForceJoinChannel) -> Optional[str]:
    """Return a usable URL for a channel, or None."""
    if ch.invite_url:
        return ch.invite_url
    if ch.username:
        # removeprefix("@") — lstrip("@") strips ANY leading '@' chars
        return f"https://t.me/{ch.username.removeprefix('@')}"
    return None


def _numbered_rows(missing_channels: List[ForceJoinChannel]) -> list:
    """
    Build rows of inline buttons, 2 per row.
    Label: '📢 Join Channel N' or uses title if present (truncated).
    """
    url_buttons = []
    for idx, ch in enumerate(missing_channels, start=1):
        url = _resolve_join_url(ch)
        if not url:
            continue

        title = getattr(ch, "title", None)
        if title:
            short = title[:18] + ("…" if len(title) > 18 else "")
            label = f"📢 {short}"
        else:
            label = f"📢 Join Channel {idx}"

        url_buttons.append(StyledButton(label, style="primary", url=url))

    # 2 buttons per row
    rows = [url_buttons[i:i + 2] for i in range(0, len(url_buttons), 2)]
    return rows


class ForceJoinService:

    # In-memory dedupe: user_id → last notified timestamp (seconds)
    _last_notified: dict = {}

    # ══════════════════════════════════════════════════════════════
    # Core membership checks
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
        """
        Build numbered join keyboard (2 per row) with a check button at the bottom.

          [📢 Join Channel 1] [📢 Join Channel 2]
          [📢 Join Channel 3]
          [✅ Joined - Check]
        """
        rows = _numbered_rows(missing_channels)
        rows.append([StyledButton(
            "✅ Joined - Check",
            style="success",
            callback_data="force_join_check",
        )])
        return InlineKeyboardMarkup(rows)

    # ══════════════════════════════════════════════════════════════
    # Periodic background check (APScheduler job)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    async def run_periodic_check(bot: Bot, batch_size: int = 100) -> dict:
        """
        Background job: scan all active users, verify force-join membership,
        and notify those who have left any required channel.
        """
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
                    continue

            if not missing_channels:
                continue

            missing_count += 1

            # Dedupe — only notify once per 6 hours per user
            now = time.time()
            last = ForceJoinService._last_notified.get(user_id, 0)
            if now - last < 6 * 3600:
                continue

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
                log.debug(
                    "Could not send force-join warning",
                    user_id=user_id,
                    error=str(e),
                )

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
        """Human-readable HTML message listing all missing channels with counts."""
        total = len(missing_channels)
        names = []
        for idx, ch in enumerate(missing_channels, start=1):
            if ch.username:
                names.append(f"{idx}. @{ch.username}")
            elif getattr(ch, "title", None):
                names.append(f"{idx}. {ch.title}")
            else:
                names.append(f"{idx}. {ch.chat_id}")

        joined = "\n".join(f"• <b>{n}</b>" for n in names)

        return (
            f"⚠️ <b>Channel Membership Required</b>\n\n"
            f"📌 You need to re-join <b>{total}</b> channel(s):\n\n"
            f"{joined}\n\n"
            f"Tap the button(s) below, then press ✅ Check."
        )

    @staticmethod
    def _build_violation_keyboard(
        missing_channels: List[ForceJoinChannel],
    ) -> InlineKeyboardMarkup:
        """Numbered re-join buttons (2 per row) + a check button."""
        rows = _numbered_rows(missing_channels)
        rows.append([StyledButton(
            "✅ Joined - Check",
            style="success",
            callback_data="force_join_check",
        )])
        return InlineKeyboardMarkup(rows)