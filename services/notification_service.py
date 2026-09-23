"""
Notification Service — async Telegram message dispatch.
All notifications are fire-and-forget (non-blocking to financial ops).
"""
from decimal import Decimal
from typing import Optional

import structlog
from telegram import Bot
from telegram.error import TelegramError

from config import settings

log = structlog.get_logger(__name__)

_bot: Optional[Bot] = None


def set_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


async def _send(chat_id: int, text: str, parse_mode: str = "HTML") -> None:
    """Send a message, silently handle errors."""
    if not _bot:
        log.warning("Notification bot not set")
        return
    try:
        await _bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except TelegramError as e:
        log.warning("Failed to send notification", chat_id=chat_id, error=str(e))


class NotificationService:

    @staticmethod
    async def task_reward_earned(user_id: int, amount: Decimal, new_balance: Decimal) -> None:
        await _send(
            user_id,
            f"✅ You earned <b>{amount:.8f} USDT</b> for completing a task!\n"
            f"💰 Balance: <b>{new_balance:.8f} USDT</b>",
        )

    @staticmethod
    async def referral_joined(referrer_id: int, reward: Decimal) -> None:
        await _send(
            referrer_id,
            f"🎁 Your referral joined! You earned <b>{reward:.8f} USDT</b>",
        )

    @staticmethod
    async def referral_commission(referrer_id: int, commission: Decimal) -> None:
        await _send(
            referrer_id,
            f"💰 Commission: <b>{commission:.8f} USDT</b> from referral activity",
        )

    @staticmethod
    async def withdrawal_created(user_id: int, amount: Decimal) -> None:
        await _send(
            user_id,
            f"📤 Withdrawal of <b>{amount:.8f} USDT</b> submitted.\n"
            f"⏳ Processing...",
        )

    @staticmethod
    async def withdrawal_paid(user_id: int, amount: Decimal, tx_hash: str) -> None:
        short_hash = f"{tx_hash[:10]}...{tx_hash[-6:]}" if tx_hash else "N/A"
        await _send(
            user_id,
            f"✅ Withdrawal <b>PAID</b>!\n"
            f"💵 Amount: <b>{amount:.8f} USDT</b>\n"
            f"🔗 TX: <code>{short_hash}</code>\n"
            f"🌐 <a href='https://bscscan.com/tx/{tx_hash}'>View on BSCScan</a>",
        )

    @staticmethod
    async def withdrawal_failed(user_id: int, amount: Decimal) -> None:
        await _send(
            user_id,
            f"❌ Withdrawal failed.\n"
            f"💰 <b>{amount:.8f} USDT</b> has been returned to your balance.\n"
            f"Please contact support if this issue persists.",
        )

    @staticmethod
    async def deposit_confirmed(sponsor_id: int, amount: Decimal) -> None:
        """Notify sponsor that deposit has been credited."""
        if not _bot:
            return
        # Get sponsor's telegram user_id
        from database import get_session
        from models.sponsor import Sponsor
        from sqlalchemy import select
        async with get_session() as session:
            result = await session.execute(
                select(Sponsor.user_id).where(Sponsor.id == sponsor_id)
            )
            user_id = result.scalar_one_or_none()

        if user_id:
            await _send(
                user_id,
                f"✅ Deposit <b>Confirmed</b>!\n"
                f"💰 Amount: <b>{amount:.8f} USDT</b> credited to your account.",
            )

    @staticmethod
    async def campaign_approved(sponsor_user_id: int, campaign_title: str) -> None:
        await _send(
            sponsor_user_id,
            f"✅ Campaign <b>{campaign_title}</b> has been approved!\n"
            f"Please fund it to make it go live.",
        )

    @staticmethod
    async def campaign_completed(sponsor_user_id: int, campaign_title: str, spent: Decimal) -> None:
        await _send(
            sponsor_user_id,
            f"✅ Campaign <b>{campaign_title}</b> completed!\n"
            f"💵 Total spent: <b>{spent:.8f} USDT</b>",
        )

    @staticmethod
    async def notify_admin_fraud(
        user_id: int,
        flag_type,
        severity,
        details: dict,
    ) -> None:
        """Notify all admins of a high-severity fraud flag."""
        msg = (
            f"🚨 <b>FRAUD FLAG</b>\n"
            f"User: <code>{user_id}</code>\n"
            f"Type: <b>{flag_type}</b>\n"
            f"Severity: <b>{severity}</b>\n"
            f"Details: {str(details)[:300]}"
        )
        for admin_id in settings.ADMIN_IDS:
            await _send(admin_id, msg)

    @staticmethod
    async def notify_admin_critical(message: str) -> None:
        """Notify all admins of a critical system event."""
        msg = f"🔴 <b>CRITICAL ALERT</b>\n{message[:800]}"
        for admin_id in settings.ADMIN_IDS:
            await _send(admin_id, msg)

    @staticmethod
    async def notify_admin_new_campaign(
        campaign_id: int, title: str, sponsor_id: int
    ) -> None:
        msg = (
            f"📋 <b>New Campaign Pending Approval</b>\n"
            f"ID: #{campaign_id}\n"
            f"Title: {title}\n"
            f"Sponsor: #{sponsor_id}"
        )
        for admin_id in settings.ADMIN_IDS:
            await _send(admin_id, msg)

    @staticmethod
    async def notify_admin_large_withdrawal(
        user_id: int, amount: Decimal, withdrawal_id: int
    ) -> None:
        msg = (
            f"⚠️ <b>Large Withdrawal Request</b>\n"
            f"User: <code>{user_id}</code>\n"
            f"Amount: <b>{amount:.8f} USDT</b>\n"
            f"Withdrawal #: {withdrawal_id}"
        )
        for admin_id in settings.ADMIN_IDS:
            await _send(admin_id, msg)
