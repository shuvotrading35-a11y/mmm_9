"""
Statistics Handler — platform-wide public stats.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from utils.decimal_utils import fmt_usdt

log = structlog.get_logger(__name__)


async def handle_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or (update.callback_query and update.callback_query.message)

    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.user import User, UserStatus
        from models.campaign import Campaign, CampaignStatus
        from models.withdrawal import Withdrawal, WithdrawalStatus
        from models.transaction import Transaction, TransactionType

        # User counts
        total_users = (await session.execute(select(sa_func.count(User.id)))).scalar() or 0
        active_users = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.ACTIVE)
        )).scalar() or 0
        banned_users = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.BANNED)
        )).scalar() or 0

        # Campaign counts
        total_campaigns = (await session.execute(select(sa_func.count(Campaign.id)))).scalar() or 0
        active_campaigns = (await session.execute(
            select(sa_func.count(Campaign.id)).where(Campaign.status == CampaignStatus.ACTIVE)
        )).scalar() or 0
        completed_campaigns = (await session.execute(
            select(sa_func.count(Campaign.id)).where(Campaign.status == CampaignStatus.COMPLETED)
        )).scalar() or 0

        # Financial totals
        rewards_paid = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).where(
                Transaction.tx_type == TransactionType.TASK_REWARD,
                Transaction.amount > 0,
            )
        )).scalar() or 0

        withdrawals_paid = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Withdrawal.amount), 0)).where(
                Withdrawal.status == WithdrawalStatus.PAID
            )
        )).scalar() or 0

        referral_rewards = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).where(
                Transaction.tx_type.in_([
                    TransactionType.REFERRAL_REWARD,
                    TransactionType.REFERRAL_COMMISSION,
                ]),
                Transaction.amount > 0,
            )
        )).scalar() or 0

    text = (
        f"📊 <b>PLATFORM STATISTICS</b>\n\n"
        f"━━━━━━ USERS ━━━━━━\n"
        f"👥 Total:      <b>{total_users:,}</b>\n"
        f"🟢 Active:     <b>{active_users:,}</b>\n"
        f"🚫 Banned:     <b>{banned_users:,}</b>\n\n"
        f"━━━━━━ CAMPAIGNS ━━━━━━\n"
        f"📋 Total:       <b>{total_campaigns:,}</b>\n"
        f"🟢 Active:      <b>{active_campaigns:,}</b>\n"
        f"✅ Completed:   <b>{completed_campaigns:,}</b>\n\n"
        f"━━━━━━ FINANCIALS ━━━━━━\n"
        f"💰 User Rewards Paid:     <b>{fmt_usdt(rewards_paid)} USDT</b>\n"
        f"💳 Withdrawals Paid:      <b>{fmt_usdt(withdrawals_paid)} USDT</b>\n"
        f"🎁 Referral Rewards:      <b>{fmt_usdt(referral_rewards)} USDT</b>\n"
    )

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        await update.callback_query.edit_message_text(text, parse_mode="HTML")
