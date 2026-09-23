"""
Referral Handler — show referral link and stats.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from database import get_session
from utils.decimal_utils import fmt_usdt

log = structlog.get_logger(__name__)


async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message or (update.callback_query and update.callback_query.message)

    async with get_session() as session:
        from models.user import User
        from services.user_service import UserService

        db_user = await session.get(User, user.id)
        if not db_user:
            await message.reply_text("Please use /start first.")
            return

        ref_stats = await UserService.get_referral_stats(session, user.id)

    ref_link = f"https://t.me/{settings.BOT_USERNAME}?start=ref_{db_user.referral_code}"
    commission_pct = int(settings.REFERRAL_COMMISSION_PCT)

    text = (
        f"🎁 <b>YOUR REFERRAL</b>\n\n"
        f"📎 Your Link:\n<code>{ref_link}</code>\n\n"
        f"📋 <b>How it works:</b>\n"
        f"• Share your link with friends\n"
        f"• Earn <b>{fmt_usdt(settings.REFERRAL_REWARD)} USDT</b> when they join\n"
        f"• Earn <b>{commission_pct}%</b> commission on every task they complete\n\n"
        f"━━━━━━ YOUR STATS ━━━━━━\n"
        f"👥 Total Referrals: <b>{ref_stats['total_referrals']}</b>\n"
        f"💵 Signup Rewards: <b>{fmt_usdt(ref_stats['signup_rewards'])} USDT</b>\n"
        f"💸 Task Commission: <b>{fmt_usdt(ref_stats['commission_earned'])} USDT</b>\n"
        f"💎 Total Earned: <b>{fmt_usdt(ref_stats['signup_rewards'] + ref_stats['commission_earned'])} USDT</b>"
    )

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Link", switch_inline_query=ref_link)],
    ])

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
