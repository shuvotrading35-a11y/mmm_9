"""
Live Payments Handler — display recent paid withdrawals.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from keyboards.user_keyboards import live_payments_keyboard
from utils.decimal_utils import fmt_usdt
from utils.time_utils import now_utc

log = structlog.get_logger(__name__)


async def handle_live_payments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent successful withdrawals (masked user IDs)."""
    async with get_session() as session:
        from sqlalchemy import select
        from models.withdrawal import Withdrawal, WithdrawalStatus
        from models.user import User

        result = await session.execute(
            select(Withdrawal, User)
            .join(User, User.id == Withdrawal.user_id)
            .where(Withdrawal.status == WithdrawalStatus.PAID)
            .order_by(Withdrawal.processed_at.desc())
            .limit(10)
        )
        rows = result.all()

    if not rows:
        text = "💰 <b>LIVE PAYMENTS</b>\n\nNo payments yet. Be the first to earn! 🚀"
    else:
        lines = ["💰 <b>LIVE PAYMENTS</b>\n\nRecent successful withdrawals:\n"]
        for withdrawal, user in rows:
            masked = user.masked_id
            time_ago = _time_ago(withdrawal.processed_at)
            lines.append(
                f"🟢 User {masked}  │  "
                f"{fmt_usdt(withdrawal.amount)} USDT  │  "
                f"BSC  │  ✅ PAID  │  {time_ago}"
            )
        text = "\n".join(lines)

    message = update.message or (update.callback_query and update.callback_query.message)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=live_payments_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=live_payments_keyboard()
        )


def _time_ago(dt) -> str:
    if not dt:
        return "N/A"
    from datetime import timezone
    delta = now_utc() - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now_utc() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60} min ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"
