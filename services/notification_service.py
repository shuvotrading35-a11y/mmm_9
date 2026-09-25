"""
Notification Service — sends messages to users via the bot.

The bot instance is injected once at startup (post_init in bot.py).
All send methods are best-effort: if the bot isn't set or the user has
blocked the bot, the failure is logged and silently ignored.
"""
import asyncio
import structlog
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

log = structlog.get_logger(__name__)


class NotificationService:
    _bot: Optional[Bot] = None

    # ══════════════════════════════════════════════════════════════
    # Bot injection (called from bot.py post_init)
    # ══════════════════════════════════════════════════════════════

    @classmethod
    def set_bot(cls, bot: Bot) -> None:
        cls._bot = bot
        log.info("NotificationService: bot set")

    # Aliases for compatibility
    @classmethod
    def init(cls, bot: Bot) -> None:
        cls.set_bot(bot)

    @classmethod
    def set_application(cls, bot: Bot) -> None:
        cls.set_bot(bot)

    @classmethod
    def configure(cls, bot: Bot) -> None:
        cls.set_bot(bot)

    # ══════════════════════════════════════════════════════════════
    # Core send
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def send_to_user(
        cls,
        user_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup=None,
    ) -> bool:
        """Send a message to a single user. Returns True on success."""
        if cls._bot is None:
            log.warning("NotificationService: bot not set — cannot send", user_id=user_id)
            return False
        try:
            await cls._bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            return True
        except TelegramError as e:
            log.debug("send_to_user failed", user_id=user_id, error=str(e))
            return False
        except Exception:
            log.exception("send_to_user unexpected error", user_id=user_id)
            return False

    # Aliases
    @classmethod
    async def send_message(cls, user_id: int, text: str, **kwargs) -> bool:
        return await cls.send_to_user(user_id, text, **kwargs)

    @classmethod
    async def notify_user(cls, user_id: int, text: str, **kwargs) -> bool:
        return await cls.send_to_user(user_id, text, **kwargs)

    # ══════════════════════════════════════════════════════════════
    # Admin notifications
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def notify_admin(cls, text: str, **kwargs) -> int:
        """Send to all admins. Returns number of successful sends."""
        from config import settings
        if not settings.ADMIN_IDS:
            return 0
        sent = 0
        for admin_id in settings.ADMIN_IDS:
            ok = await cls.send_to_user(admin_id, text, **kwargs)
            if ok:
                sent += 1
        return sent

    @classmethod
    async def notify_admin_new_user(
        cls,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        referrer_id: Optional[int] = None,
        total_users: Optional[int] = None,
        language_code: Optional[str] = None,
        is_premium: bool = False,
    ) -> None:
        """Notify all admins that a new user has registered."""
        name_parts = [first_name or "", last_name or ""]
        full_name = " ".join(p for p in name_parts if p).strip() or "—"
        username_str = f"@{username}" if username else "—"

        premium_badge = " ⭐" if is_premium else ""
        lang_line = f"\n🌐 Language: {language_code}" if language_code else ""
        referrer_line = ""
        if referrer_id:
            referrer_line = f"\n🎁 Referred by: <code>{referrer_id}</code>"
        total_line = ""
        if total_users is not None:
            total_line = f"\n\n📊 Total users: <b>{total_users:,}</b>"

        text = (
            f"🆕 <b>New User Registered</b>{premium_badge}\n\n"
            f"👤 Name: <b>{full_name}</b>\n"
            f"🔗 Username: {username_str}\n"
            f"🆔 ID: <code>{user_id}</code>"
            f"{lang_line}"
            f"{referrer_line}"
            f"{total_line}"
        )
        await cls.notify_admin(text)

    @classmethod
    async def notify_admin_new_campaign(
        cls, campaign_id: int, title: str, sponsor_user_id: int
    ) -> None:
        """Notify all admins about a new campaign awaiting approval."""
        text = (
            f"🆕 <b>New Campaign Submitted</b>\n\n"
            f"📌 ID: <b>#{campaign_id}</b>\n"
            f"📝 Title: {title}\n"
            f"👤 Sponsor: <code>{sponsor_user_id}</code>\n\n"
            f"Open /admin → 📋 Campaigns to review."
        )
        await cls.notify_admin(text)

    @classmethod
    async def notify_admin_new_deposit(
        cls, deposit_id: int, sponsor_user_id: int, amount: str, tx_hash: str
    ) -> None:
        text = (
            f"💰 <b>New Deposit Pending</b>\n\n"
            f"📌 ID: <b>#{deposit_id}</b>\n"
            f"👤 Sponsor: <code>{sponsor_user_id}</code>\n"
            f"💵 Amount: <b>{amount} USDT</b>\n"
            f"🔗 TX: <code>{tx_hash[:20]}…</code>\n\n"
            f"Open /admin → 💰 Deposits to approve."
        )
        await cls.notify_admin(text)

    @classmethod
    async def notify_admin_new_withdrawal(
        cls, withdrawal_id: int, user_id: int, amount: str
    ) -> None:
        text = (
            f"💳 <b>New Withdrawal Request</b>\n\n"
            f"📌 ID: <b>#{withdrawal_id}</b>\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"💵 Amount: <b>{amount} USDT</b>\n\n"
            f"Open /admin → 💳 Withdrawals to process."
        )
        await cls.notify_admin(text)

    # ══════════════════════════════════════════════════════════════
    # Campaign lifecycle (sponsor-facing)
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def campaign_approved(
        cls, sponsor_user_id: int, campaign_title: str
    ) -> None:
        """Notify sponsor that their campaign was approved."""
        await cls.send_to_user(
            sponsor_user_id,
            f"✅ <b>Campaign Approved</b>\n\n"
            f"📝 <b>{campaign_title}</b>\n\n"
            f"Your campaign is now pending funding.\n"
            f"Open /sponsor → 📋 My Campaigns → tap the campaign → "
            f"💰 Fund Campaign to activate it.",
        )

    @classmethod
    async def campaign_rejected(
        cls, sponsor_user_id: int, campaign_title: str
    ) -> None:
        await cls.send_to_user(
            sponsor_user_id,
            f"❌ <b>Campaign Rejected</b>\n\n"
            f"📝 <b>{campaign_title}</b>\n\n"
            f"Contact support for details.",
        )

    @classmethod
    async def campaign_funded(
        cls, sponsor_user_id: int, campaign_title: str, budget: str
    ) -> None:
        await cls.send_to_user(
            sponsor_user_id,
            f"🎉 <b>Campaign Now Active</b>\n\n"
            f"📝 <b>{campaign_title}</b>\n"
            f"💵 Budget: <b>{budget} USDT</b>\n\n"
            f"Users will start seeing it in /tasks.",
        )

    @classmethod
    async def campaign_expired(
        cls, sponsor_user_id: int, campaign_title: str, refund: str
    ) -> None:
        await cls.send_to_user(
            sponsor_user_id,
            f"⌛ <b>Campaign Expired</b>\n\n"
            f"📝 <b>{campaign_title}</b>\n"
            f"💰 Refunded to your balance: <b>{refund} USDT</b>",
        )

    # ══════════════════════════════════════════════════════════════
    # Referral notifications
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def referral_joined(
        cls, referrer_user_id: int, reward: str
    ) -> None:
        """Notify referrer that someone joined through their link."""
        await cls.send_to_user(
            referrer_user_id,
            f"🎁 <b>New Referral!</b>\n\n"
            f"Someone joined using your referral link.\n"
            f"💰 You earned: <b>{reward} USDT</b>",
        )

    @classmethod
    async def referral_commission(
        cls, referrer_user_id: int, commission: str, referred_name: str = ""
    ) -> None:
        await cls.send_to_user(
            referrer_user_id,
            f"💸 <b>Referral Commission</b>\n\n"
            f"Your referral{' ' + referred_name if referred_name else ''} "
            f"completed a task.\n"
            f"💰 Commission: <b>{commission} USDT</b>",
        )

    # ══════════════════════════════════════════════════════════════
    # Balance / deposit / withdrawal (user-facing)
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def balance_credited(
        cls, user_id: int, amount: str, new_balance: str, note: str = ""
    ) -> None:
        msg = (
            f"✅ <b>Balance Credited</b>\n\n"
            f"➕ Amount: <b>+{amount} USDT</b>\n"
            f"💰 New balance: <b>{new_balance} USDT</b>"
        )
        if note:
            msg += f"\n\n📝 {note}"
        await cls.send_to_user(user_id, msg)

    @classmethod
    async def balance_debited(
        cls, user_id: int, amount: str, new_balance: str, note: str = ""
    ) -> None:
        msg = (
            f"✅ <b>Balance Debited</b>\n\n"
            f"➖ Amount: <b>-{amount} USDT</b>\n"
            f"💰 New balance: <b>{new_balance} USDT</b>"
        )
        if note:
            msg += f"\n\n📝 {note}"
        await cls.send_to_user(user_id, msg)

    @classmethod
    async def deposit_confirmed(
        cls, user_id: int, amount: str, new_balance: str
    ) -> None:
        await cls.send_to_user(
            user_id,
            f"💰 <b>Deposit Confirmed</b>\n\n"
            f"➕ Amount: <b>{amount} USDT</b>\n"
            f"💳 New balance: <b>{new_balance} USDT</b>",
        )

    @classmethod
    async def withdrawal_approved(
        cls, user_id: int, amount: str, wallet: str
    ) -> None:
        await cls.send_to_user(
            user_id,
            f"✅ <b>Withdrawal Approved</b>\n\n"
            f"💵 Amount: <b>{amount} USDT</b>\n"
            f"🏦 Wallet: <code>{wallet}</code>\n\n"
            f"Funds are on the way.",
        )

    @classmethod
    async def withdrawal_rejected(
        cls, user_id: int, amount: str, reason: str = ""
    ) -> None:
        msg = (
            f"❌ <b>Withdrawal Rejected</b>\n\n"
            f"💵 Amount: <b>{amount} USDT</b>\n"
            f"💰 Refunded to your balance."
        )
        if reason:
            msg += f"\n\n📝 Reason: {reason}"
        await cls.send_to_user(user_id, msg)

    # ══════════════════════════════════════════════════════════════
    # Task / reward notifications
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def task_reward(
        cls, user_id: int, amount: str, new_balance: str, task_title: str = ""
    ) -> None:
        msg = (
            f"🎉 <b>Task Reward Earned!</b>\n\n"
        )
        if task_title:
            msg += f"📝 {task_title}\n"
        msg += (
            f"💰 Reward: <b>+{amount} USDT</b>\n"
            f"💳 New balance: <b>{new_balance} USDT</b>"
        )
        await cls.send_to_user(user_id, msg)

    @classmethod
    async def task_failed(cls, user_id: int, task_title: str, reason: str = "") -> None:
        msg = (
            f"⚠️ <b>Task Verification Failed</b>\n\n"
            f"📝 {task_title}"
        )
        if reason:
            msg += f"\n\n{reason}"
        await cls.send_to_user(user_id, msg)

    # ══════════════════════════════════════════════════════════════
    # Sponsor-facing
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def sponsor_approved(cls, sponsor_user_id: int) -> None:
        await cls.send_to_user(
            sponsor_user_id,
            f"✅ <b>Sponsor Account Approved</b>\n\n"
            f"You can now create campaigns.\n"
            f"Open /sponsor to get started.",
        )

    @classmethod
    async def sponsor_rejected(cls, sponsor_user_id: int, reason: str = "") -> None:
        msg = f"❌ <b>Sponsor Application Rejected</b>"
        if reason:
            msg += f"\n\n📝 {reason}"
        await cls.send_to_user(sponsor_user_id, msg)

    # ══════════════════════════════════════════════════════════════
    # Force-join violation
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def force_join_left(
        cls, user_id: int, channel_label: str, join_url: str = ""
    ) -> None:
        msg = (
            f"❌ <b>Channel Left Detected</b>\n\n"
            f"You have left <b>{channel_label}</b>.\n\n"
            f"To keep using this bot, please re-join:"
        )
        await cls.send_to_user(user_id, msg)

    # ══════════════════════════════════════════════════════════════
    # Broadcast helper
    # ══════════════════════════════════════════════════════════════

    @classmethod
    async def broadcast(cls, user_ids, text: str, delay: float = 0.05) -> dict:
        """Send a message to many users. Returns {sent, failed}."""
        sent = 0
        failed = 0
        for uid in user_ids:
            ok = await cls.send_to_user(uid, text)
            if ok:
                sent += 1
            else:
                failed += 1
            await asyncio.sleep(delay)
        return {"sent": sent, "failed": failed}