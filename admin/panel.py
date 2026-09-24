"""
Admin Panel — main entry point and callback router.
All handlers verify admin authorization on every call.
"""
import structlog
from decimal import Decimal
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from config import settings
from database import get_session
from keyboards.admin_keyboards import (
    admin_main_reply_keyboard,
    admin_back_reply_keyboard,
    admin_cancel_reply_keyboard,
    user_action_keyboard,
    campaign_action_keyboard,
    withdrawal_action_keyboard,
    sponsor_action_keyboard,
)
from utils.decimal_utils import fmt_usdt
from utils.time_utils import fmt_datetime

log = structlog.get_logger(__name__)


def _require_admin(user_id: int) -> bool:
    return settings.is_admin(user_id)


# ══════════════════════════════════════════════════════════════════
# Entry points
# ══════════════════════════════════════════════════════════════════

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point — /admin command. Sends reply keyboard."""
    user = update.effective_user
    if not _require_admin(user.id):
        return

    await update.message.reply_text(
        "🛡 <b>ADMIN PANEL</b>\n\nSelect an option:",
        parse_mode="HTML",
        reply_markup=admin_main_reply_keyboard(),
    )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all admin: inline callbacks (kept for per-item actions)."""
    query = update.callback_query
    user = update.effective_user

    if not _require_admin(user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return

    await query.answer()
    data = query.data
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "users":
        await _admin_users(query)
    elif action == "campaigns":
        await _admin_campaigns(query)
    elif action == "withdrawals":
        await _admin_withdrawals(query)
    elif action == "sponsors":
        await _admin_sponsors(query)
    elif action == "deposits":
        await _admin_deposits(query)
    elif action == "stats":
        await _admin_stats(query)
    elif action == "fraud":
        await _admin_fraud(query)
    elif action == "settings":
        await _admin_settings(query)
    elif action == "broadcast":
        await _admin_broadcast_prompt(query, context)
    elif action == "audit":
        await _admin_audit(query)

    # ── View branches ──
    elif action == "sponsor_view" and len(parts) > 2:
        await _admin_view_sponsor(query, int(parts[2]))
    elif action == "campaign_view" and len(parts) > 2:
        await _admin_view_campaign(query, int(parts[2]))
    elif action == "wd_view" and len(parts) > 2:
        await _admin_view_withdrawal(query, int(parts[2]))
    elif action == "banned":
        await _admin_banned_list(query)
    elif action == "flagged":
        await _admin_flagged_list(query)
    elif action == "user_search":
        await _admin_user_search_prompt(query)

    elif action == "back":
        await query.edit_message_text(
            "🛡 <b>ADMIN PANEL</b>",
            parse_mode="HTML",
        )
    elif action.startswith("ban") and len(parts) > 2:
        await _admin_ban_user(query, int(parts[2]), user.id)
    elif action.startswith("unban") and len(parts) > 2:
        await _admin_unban_user(query, int(parts[2]), user.id)
    elif action.startswith("campaign_approve") and len(parts) > 2:
        await _admin_approve_campaign(query, int(parts[2]), user.id)
    elif action.startswith("campaign_reject") and len(parts) > 2:
        await _admin_reject_campaign(query, int(parts[2]), user.id)
    elif action.startswith("campaign_pause") and len(parts) > 2:
        await _admin_pause_campaign(query, int(parts[2]), user.id)
    elif action.startswith("campaign_resume") and len(parts) > 2:
        await _admin_resume_campaign(query, int(parts[2]), user.id)
    elif action.startswith("sponsor_approve") and len(parts) > 2:
        await _admin_approve_sponsor(query, int(parts[2]), user.id)
    elif action.startswith("sponsor_reject") and len(parts) > 2:
        await _admin_reject_sponsor(query, int(parts[2]), user.id)
    elif action.startswith("sponsor_suspend") and len(parts) > 2:
        await _admin_suspend_sponsor(query, int(parts[2]), user.id)
    elif action.startswith("sponsor_add_balance") and len(parts) > 2:
        await _admin_sponsor_add_balance_prompt(query, context, int(parts[2]))
    elif action.startswith("sponsor_balance_confirm") and len(parts) > 2:
        await _admin_sponsor_balance_confirm(query, context, int(parts[2]), user.id)
    elif action.startswith("wd_approve") and len(parts) > 2:
        await _admin_approve_withdrawal(query, int(parts[2]), user.id)
    elif action.startswith("wd_reject") and len(parts) > 2:
        await _admin_reject_withdrawal(query, int(parts[2]), user.id)
    else:
        await query.edit_message_text(
            f"❓ Unknown action: <code>{data}</code>",
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════════════════════
# Reply keyboard handlers — show data directly (no filter step)
# ══════════════════════════════════════════════════════════════════

async def admin_panel_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛡 <b>ADMIN PANEL</b>\n\nSelect an option:",
        parse_mode="HTML",
        reply_markup=admin_main_reply_keyboard(),
    )


async def admin_users_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """👥 Users — show counts + inline actions directly."""
    if not _require_admin(update.effective_user.id):
        return

    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.user import User, UserStatus

        total = (await session.execute(select(sa_func.count(User.id)))).scalar()
        active = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.ACTIVE)
        )).scalar()
        banned = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.BANNED)
        )).scalar()
        flagged = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.FLAGGED)
        )).scalar()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search User", callback_data="admin:user_search")],
        [InlineKeyboardButton("🚫 View Banned", callback_data="admin:banned")],
        [InlineKeyboardButton("⚠️ View Flagged", callback_data="admin:flagged")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")],
    ])

    await update.message.reply_text(
        f"👥 <b>USERS</b>\n\n"
        f"Total: <b>{total:,}</b>\n"
        f"Active: <b>{active:,}</b>\n"
        f"Flagged: <b>{flagged:,}</b>\n"
        f"Banned: <b>{banned:,}</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def admin_campaigns_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📋 Campaigns — show counts + pending list directly."""
    if not _require_admin(update.effective_user.id):
        return

    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.campaign import Campaign, CampaignStatus

        counts = {}
        for status in CampaignStatus:
            count = (await session.execute(
                select(sa_func.count(Campaign.id)).where(Campaign.status == status)
            )).scalar()
            counts[status] = count

        pending = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.PENDING).limit(5)
        )
        pending_list = pending.scalars().all()

    buttons = []
    for c in pending_list:
        buttons.append([InlineKeyboardButton(
            f"⏳ #{c.id}: {c.title[:30]}",
            callback_data=f"admin:campaign_view:{c.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    status_lines = "\n".join(
        f"{s.value}: <b>{counts[s]:,}</b>" for s in CampaignStatus
    )

    await update.message.reply_text(
        f"📋 <b>CAMPAIGNS</b>\n\n{status_lines}\n\n"
        + ("⏳ <b>Pending Approval:</b>" if pending_list else "✅ No pending campaigns"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_sponsors_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select
        from models.sponsor import Sponsor, SponsorStatus

        pending = await session.execute(
            select(Sponsor).where(Sponsor.status == SponsorStatus.PENDING).limit(5)
        )
        pending_list = pending.scalars().all()

    buttons = []
    for s in pending_list:
        buttons.append([InlineKeyboardButton(
            f"⏳ Sponsor #{s.id} (user {s.user_id})",
            callback_data=f"admin:sponsor_view:{s.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    text = (
        f"💼 <b>SPONSORS</b>\n\n"
        f"Pending approval: <b>{len(pending_list)}</b>"
    )

    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_deposits_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.deposit import Deposit, DepositStatus

        total_confirmed = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Deposit.amount), 0))
            .where(Deposit.status == DepositStatus.CONFIRMED)
        )).scalar()
        pending_count = (await session.execute(
            select(sa_func.count(Deposit.id))
            .where(Deposit.status == DepositStatus.PENDING)
        )).scalar()

    await update.message.reply_text(
        f"💰 <b>DEPOSITS</b>\n\n"
        f"Total confirmed: <b>{fmt_usdt(total_confirmed)} USDT</b>\n"
        f"Pending verification: <b>{pending_count}</b>",
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_withdrawals_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💳 Withdrawals — show pending list directly."""
    if not _require_admin(update.effective_user.id):
        return

    async with get_session() as session:
        from sqlalchemy import select
        from models.withdrawal import Withdrawal, WithdrawalStatus

        pending = await session.execute(
            select(Withdrawal)
            .where(Withdrawal.status == WithdrawalStatus.PENDING)
            .order_by(Withdrawal.created_at.asc())
            .limit(10)
        )
        pending_list = pending.scalars().all()

    buttons = []
    for wd in pending_list:
        buttons.append([InlineKeyboardButton(
            f"💵 #{wd.id} — {fmt_usdt(wd.amount)} USDT",
            callback_data=f"admin:wd_view:{wd.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    text = f"💳 <b>WITHDRAWALS</b>\n\nPending: <b>{len(pending_list)}</b>"

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_referrals_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.referral import Referral

        total = (await session.execute(select(sa_func.count(Referral.id)))).scalar()
        paid = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Referral.reward_paid), 0))
        )).scalar()

    await update.message.reply_text(
        f"🎁 <b>REFERRALS</b>\n\n"
        f"Total referrals: <b>{total:,}</b>\n"
        f"Signup rewards paid: <b>{fmt_usdt(paid)} USDT</b>",
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_stats_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.user import User
        from models.campaign import Campaign, CampaignStatus
        from models.transaction import Transaction, TransactionType
        from models.deposit import Deposit, DepositStatus

        total_users = (await session.execute(select(sa_func.count(User.id)))).scalar()
        active_campaigns = (await session.execute(
            select(sa_func.count(Campaign.id))
            .where(Campaign.status == CampaignStatus.ACTIVE)
        )).scalar()
        total_rewards = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Transaction.amount), 0))
            .where(Transaction.tx_type == TransactionType.TASK_REWARD, Transaction.amount > 0)
        )).scalar()
        total_deposits = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Deposit.amount), 0))
            .where(Deposit.status == DepositStatus.CONFIRMED)
        )).scalar()

    await update.message.reply_text(
        f"📊 <b>PLATFORM STATS</b>\n\n"
        f"👥 Users: <b>{total_users:,}</b>\n"
        f"📋 Active Campaigns: <b>{active_campaigns}</b>\n"
        f"💰 Total Rewards: <b>{fmt_usdt(total_rewards)} USDT</b>\n"
        f"💵 Total Deposits: <b>{fmt_usdt(total_deposits)} USDT</b>",
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_broadcast_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    context.user_data["admin_awaiting_broadcast"] = True
    await update.message.reply_text(
        "📢 <b>BROADCAST</b>\n\n"
        "Send the message you want to broadcast to ALL users.\n\n"
        "⚠️ This cannot be undone.",
        parse_mode="HTML",
        reply_markup=admin_cancel_reply_keyboard(),
    )


async def admin_banned_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select
        from models.user import User, UserStatus

        result = await session.execute(
            select(User).where(User.status == UserStatus.BANNED).limit(20)
        )
        banned = result.scalars().all()

    lines = ["🚫 <b>BANNED USERS</b>\n"]
    for u in banned:
        lines.append(f"• <code>{u.id}</code> @{u.username or '—'}")
    if not banned:
        lines.append("No banned users.")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_settings_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        f"⚙️ <b>PLATFORM SETTINGS</b>\n\n"
        f"Min Withdrawal: <b>{settings.MIN_WITHDRAWAL} USDT</b>\n"
        f"Max Withdrawal: <b>{settings.MAX_WITHDRAWAL} USDT</b>\n"
        f"Referral Reward: <b>{settings.REFERRAL_REWARD} USDT</b>\n"
        f"Commission: <b>{settings.REFERRAL_COMMISSION_PCT}%</b>\n"
        f"Auto Payout: <b>{'ON' if settings.AUTO_PAYOUT_ENABLED else 'OFF'}</b>\n"
        f"Maintenance: <b>{'ON' if settings.MAINTENANCE_MODE else 'OFF'}</b>\n"
        f"Force Join: <b>{'ON' if settings.FORCE_JOIN_ENABLED else 'OFF'}</b>\n"
        f"Fraud Auto-Ban Score: <b>{settings.FRAUD_AUTO_BAN_SCORE}</b>",
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_fraud_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.fraud_flag import FraudFlag, FlagSeverity

        unreviewed = (await session.execute(
            select(sa_func.count(FraudFlag.id)).where(FraudFlag.reviewed == False)
        )).scalar()
        critical = (await session.execute(
            select(sa_func.count(FraudFlag.id))
            .where(FraudFlag.reviewed == False, FraudFlag.severity == FlagSeverity.CRITICAL)
        )).scalar()
        high = (await session.execute(
            select(sa_func.count(FraudFlag.id))
            .where(FraudFlag.reviewed == False, FraudFlag.severity == FlagSeverity.HIGH)
        )).scalar()

    await update.message.reply_text(
        f"🛡 <b>FRAUD MONITOR</b>\n\n"
        f"Unreviewed flags: <b>{unreviewed}</b>\n"
        f"🔴 Critical: <b>{critical}</b>\n"
        f"🟠 High: <b>{high}</b>",
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_audit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    async with get_session() as session:
        from sqlalchemy import select
        from models.audit_log import AuditLog

        result = await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
        )
        logs = result.scalars().all()

    lines = ["📜 <b>AUDIT LOGS (Last 10)</b>\n"]
    for entry in logs:
        lines.append(
            f"• [{fmt_datetime(entry.created_at)}] "
            f"Admin {entry.admin_id}: {entry.action} on {entry.target_type} #{entry.target_id}"
        )
    if not logs:
        lines.append("No audit logs yet.")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=admin_back_reply_keyboard(),
    )


async def admin_back_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛡 <b>ADMIN PANEL</b>",
        parse_mode="HTML",
        reply_markup=admin_main_reply_keyboard(),
    )


async def admin_close_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    from telegram import ReplyKeyboardRemove
    await update.message.reply_text(
        "Admin panel closed.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def admin_cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    context.user_data.pop("admin_awaiting_broadcast", None)
    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=admin_main_reply_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════
# Internal renderers (used by callbacks)
# ══════════════════════════════════════════════════════════════════

async def _admin_users(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.user import User, UserStatus

        total = (await session.execute(select(sa_func.count(User.id)))).scalar()
        active = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.ACTIVE)
        )).scalar()
        banned = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.BANNED)
        )).scalar()
        flagged = (await session.execute(
            select(sa_func.count(User.id)).where(User.status == UserStatus.FLAGGED)
        )).scalar()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search User", callback_data="admin:user_search")],
        [InlineKeyboardButton("🚫 View Banned", callback_data="admin:banned")],
        [InlineKeyboardButton("⚠️ View Flagged", callback_data="admin:flagged")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin:back")],
    ])

    await query.edit_message_text(
        f"👥 <b>USERS</b>\n\n"
        f"Total: <b>{total:,}</b>\n"
        f"Active: <b>{active:,}</b>\n"
        f"Flagged: <b>{flagged:,}</b>\n"
        f"Banned: <b>{banned:,}</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _admin_user_search_prompt(query) -> None:
    await query.edit_message_text(
        "🔍 <b>SEARCH USER</b>\n\n"
        "Send the user ID to search (or use /admin to go back).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:users")]
        ]),
    )


async def _admin_campaigns(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.campaign import Campaign, CampaignStatus

        counts = {}
        for status in CampaignStatus:
            count = (await session.execute(
                select(sa_func.count(Campaign.id)).where(Campaign.status == status)
            )).scalar()
            counts[status] = count

        pending = await session.execute(
            select(Campaign).where(Campaign.status == CampaignStatus.PENDING).limit(5)
        )
        pending_list = pending.scalars().all()

    buttons = []
    for c in pending_list:
        buttons.append([InlineKeyboardButton(
            f"⏳ #{c.id}: {c.title[:30]}",
            callback_data=f"admin:campaign_view:{c.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    status_lines = "\n".join(
        f"{s.value}: <b>{counts[s]:,}</b>" for s in CampaignStatus
    )

    await query.edit_message_text(
        f"📋 <b>CAMPAIGNS</b>\n\n{status_lines}\n\n"
        + ("⏳ <b>Pending Approval:</b>" if pending_list else "✅ No pending campaigns"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _admin_withdrawals(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.withdrawal import Withdrawal, WithdrawalStatus

        pending = await session.execute(
            select(Withdrawal)
            .where(Withdrawal.status == WithdrawalStatus.PENDING)
            .order_by(Withdrawal.created_at.asc())
            .limit(10)
        )
        pending_list = pending.scalars().all()

    buttons = []
    for wd in pending_list:
        buttons.append([InlineKeyboardButton(
            f"💵 #{wd.id} — {fmt_usdt(wd.amount)} USDT",
            callback_data=f"admin:wd_view:{wd.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    await query.edit_message_text(
        f"💳 <b>WITHDRAWALS</b>\n\nPending: <b>{len(pending_list)}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _admin_sponsors(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.sponsor import Sponsor, SponsorStatus

        pending = await session.execute(
            select(Sponsor).where(Sponsor.status == SponsorStatus.PENDING).limit(5)
        )
        pending_list = pending.scalars().all()

    buttons = []
    for s in pending_list:
        buttons.append([InlineKeyboardButton(
            f"⏳ Sponsor #{s.id} (user {s.user_id})",
            callback_data=f"admin:sponsor_view:{s.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    await query.edit_message_text(
        f"💼 <b>SPONSORS</b>\n\nPending approval: <b>{len(pending_list)}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _admin_deposits(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.deposit import Deposit, DepositStatus

        total_confirmed = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Deposit.amount), 0))
            .where(Deposit.status == DepositStatus.CONFIRMED)
        )).scalar()
        pending_count = (await session.execute(
            select(sa_func.count(Deposit.id))
            .where(Deposit.status == DepositStatus.PENDING)
        )).scalar()

    await query.edit_message_text(
        f"💰 <b>DEPOSITS</b>\n\n"
        f"Total confirmed: <b>{fmt_usdt(total_confirmed)} USDT</b>\n"
        f"Pending verification: <b>{pending_count}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_stats(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.user import User
        from models.campaign import Campaign, CampaignStatus
        from models.transaction import Transaction, TransactionType
        from models.deposit import Deposit, DepositStatus

        total_users = (await session.execute(select(sa_func.count(User.id)))).scalar()
        active_campaigns = (await session.execute(
            select(sa_func.count(Campaign.id)).where(Campaign.status == CampaignStatus.ACTIVE)
        )).scalar()
        total_rewards = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Transaction.amount), 0))
            .where(Transaction.tx_type == TransactionType.TASK_REWARD, Transaction.amount > 0)
        )).scalar()
        total_deposits = (await session.execute(
            select(sa_func.coalesce(sa_func.sum(Deposit.amount), 0))
            .where(Deposit.status == DepositStatus.CONFIRMED)
        )).scalar()

    await query.edit_message_text(
        f"📊 <b>PLATFORM STATS</b>\n\n"
        f"👥 Users: <b>{total_users:,}</b>\n"
        f"📋 Active Campaigns: <b>{active_campaigns}</b>\n"
        f"💰 Total Rewards: <b>{fmt_usdt(total_rewards)} USDT</b>\n"
        f"💵 Total Deposits: <b>{fmt_usdt(total_deposits)} USDT</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_fraud(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select, func as sa_func
        from models.fraud_flag import FraudFlag, FlagSeverity

        unreviewed = (await session.execute(
            select(sa_func.count(FraudFlag.id)).where(FraudFlag.reviewed == False)
        )).scalar()
        critical = (await session.execute(
            select(sa_func.count(FraudFlag.id))
            .where(FraudFlag.reviewed == False, FraudFlag.severity == FlagSeverity.CRITICAL)
        )).scalar()
        high = (await session.execute(
            select(sa_func.count(FraudFlag.id))
            .where(FraudFlag.reviewed == False, FraudFlag.severity == FlagSeverity.HIGH)
        )).scalar()

    await query.edit_message_text(
        f"🛡 <b>FRAUD MONITOR</b>\n\n"
        f"Unreviewed flags: <b>{unreviewed}</b>\n"
        f"🔴 Critical: <b>{critical}</b>\n"
        f"🟠 High: <b>{high}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_settings(query) -> None:
    await query.edit_message_text(
        f"⚙️ <b>PLATFORM SETTINGS</b>\n\n"
        f"Min Withdrawal: <b>{settings.MIN_WITHDRAWAL} USDT</b>\n"
        f"Max Withdrawal: <b>{settings.MAX_WITHDRAWAL} USDT</b>\n"
        f"Referral Reward: <b>{settings.REFERRAL_REWARD} USDT</b>\n"
        f"Commission: <b>{settings.REFERRAL_COMMISSION_PCT}%</b>\n"
        f"Auto Payout: <b>{'ON' if settings.AUTO_PAYOUT_ENABLED else 'OFF'}</b>\n"
        f"Maintenance: <b>{'ON' if settings.MAINTENANCE_MODE else 'OFF'}</b>\n"
        f"Force Join: <b>{'ON' if settings.FORCE_JOIN_ENABLED else 'OFF'}</b>\n"
        f"Fraud Auto-Ban Score: <b>{settings.FRAUD_AUTO_BAN_SCORE}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_audit(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.audit_log import AuditLog

        result = await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(5)
        )
        logs = result.scalars().all()

    lines = ["📜 <b>AUDIT LOGS (Last 5)</b>\n"]
    for entry in logs:
        lines.append(
            f"• [{fmt_datetime(entry.created_at)}] "
            f"Admin {entry.admin_id}: {entry.action} on {entry.target_type} #{entry.target_id}"
        )
    if not logs:
        lines.append("No audit logs yet.")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_broadcast_prompt(query, context) -> None:
    context.user_data["awaiting_broadcast"] = True
    await query.edit_message_text(
        "📢 <b>BROADCAST</b>\n\nSend your message to broadcast to ALL users.\n\n"
        "⚠️ This cannot be undone.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:back")]
        ]),
    )


# ══════════════════════════════════════════════════════════════════
# Action handlers
# ══════════════════════════════════════════════════════════════════

async def _admin_ban_user(query, target_user_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.user import User, UserStatus
            from models.audit_log import AuditLog

            user = await session.get(User, target_user_id)
            if not user:
                await query.edit_message_text("❌ User not found.")
                return

            old_status = user.status
            user.status = UserStatus.BANNED

            session.add(AuditLog(
                admin_id=admin_id,
                action="BAN_USER",
                target_type="user",
                target_id=target_user_id,
                old_value={"status": old_status.value if hasattr(old_status, "value") else str(old_status)},
                new_value={"status": "BANNED"},
            ))

    await query.edit_message_text(
        f"✅ User {target_user_id} has been banned.",
        reply_markup=user_action_keyboard(target_user_id, "BANNED"),
    )


async def _admin_unban_user(query, target_user_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.user import User, UserStatus
            from models.audit_log import AuditLog

            user = await session.get(User, target_user_id)
            if not user:
                await query.edit_message_text("❌ User not found.")
                return

            user.status = UserStatus.ACTIVE
            session.add(AuditLog(
                admin_id=admin_id,
                action="UNBAN_USER",
                target_type="user",
                target_id=target_user_id,
                old_value={"status": "BANNED"},
                new_value={"status": "ACTIVE"},
            ))

    await query.edit_message_text(f"✅ User {target_user_id} has been unbanned.")


async def _admin_approve_campaign(query, campaign_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from services.campaign_service import CampaignService
            from models.audit_log import AuditLog

            await CampaignService.approve_campaign(session, campaign_id, admin_id)
            session.add(AuditLog(
                admin_id=admin_id,
                action="APPROVE_CAMPAIGN",
                target_type="campaign",
                target_id=campaign_id,
            ))

    await query.edit_message_text(
        f"✅ Campaign #{campaign_id} approved and pending funding."
    )


async def _admin_reject_campaign(query, campaign_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.campaign import Campaign, CampaignStatus
            from models.audit_log import AuditLog

            campaign = await session.get(Campaign, campaign_id)
            if campaign:
                campaign.status = CampaignStatus.CANCELLED
            session.add(AuditLog(
                admin_id=admin_id,
                action="REJECT_CAMPAIGN",
                target_type="campaign",
                target_id=campaign_id,
            ))

    await query.edit_message_text(f"❌ Campaign #{campaign_id} rejected.")


async def _admin_pause_campaign(query, campaign_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from services.campaign_service import CampaignService
            await CampaignService.pause_campaign(session, campaign_id, admin_id)

    await query.edit_message_text(f"⏸ Campaign #{campaign_id} paused.")


async def _admin_resume_campaign(query, campaign_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.campaign import Campaign, CampaignStatus
            from models.audit_log import AuditLog

            campaign = await session.get(Campaign, campaign_id)
            if campaign and campaign.status == CampaignStatus.PAUSED:
                campaign.status = CampaignStatus.ACTIVE
            session.add(AuditLog(
                admin_id=admin_id,
                action="RESUME_CAMPAIGN",
                target_type="campaign",
                target_id=campaign_id,
            ))

    await query.edit_message_text(f"▶️ Campaign #{campaign_id} resumed.")


async def _admin_approve_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from services.sponsor_service import SponsorService
            await SponsorService.approve_sponsor(session, sponsor_id, admin_id)

    await query.edit_message_text(f"✅ Sponsor #{sponsor_id} approved.")


async def _admin_reject_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.sponsor import Sponsor, SponsorStatus
            from models.audit_log import AuditLog

            sponsor = await session.get(Sponsor, sponsor_id)
            if sponsor:
                sponsor.status = SponsorStatus.REJECTED
            session.add(AuditLog(
                admin_id=admin_id,
                action="REJECT_SPONSOR",
                target_type="sponsor",
                target_id=sponsor_id,
            ))

    await query.edit_message_text(f"❌ Sponsor #{sponsor_id} rejected.")


async def _admin_suspend_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.sponsor import Sponsor, SponsorStatus
            from models.audit_log import AuditLog

            sponsor = await session.get(Sponsor, sponsor_id)
            if sponsor:
                sponsor.status = SponsorStatus.SUSPENDED
            session.add(AuditLog(
                admin_id=admin_id,
                action="SUSPEND_SPONSOR",
                target_type="sponsor",
                target_id=sponsor_id,
            ))

    await query.edit_message_text(f"🚫 Sponsor #{sponsor_id} suspended.")


async def _admin_approve_withdrawal(query, withdrawal_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from services.withdrawal_service import WithdrawalService
            success = await WithdrawalService.process_withdrawal(session, withdrawal_id)

    if success:
        await query.edit_message_text(f"✅ Withdrawal #{withdrawal_id} processed successfully.")
    else:
        await query.edit_message_text(f"❌ Withdrawal #{withdrawal_id} processing failed. User refunded.")


async def _admin_reject_withdrawal(query, withdrawal_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.withdrawal import Withdrawal, WithdrawalStatus
            from services.withdrawal_service import WithdrawalService

            wd = await session.get(Withdrawal, withdrawal_id)
            if wd and wd.status == WithdrawalStatus.PENDING:
                await WithdrawalService._refund_failed_withdrawal(
                    session, wd, "Rejected by admin"
                )

    await query.edit_message_text(f"❌ Withdrawal #{withdrawal_id} rejected. User refunded.")


# ══════════════════════════════════════════════════════════════════
# View handlers — sponsor / campaign / withdrawal detail
# ══════════════════════════════════════════════════════════════════

async def _admin_view_sponsor(query, sponsor_id: int) -> None:
    async with get_session() as session:
        from models.sponsor import Sponsor
        from models.user import User

        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            await query.edit_message_text("❌ Sponsor not found.")
            return

        user = await session.get(User, sponsor.user_id)

    username = f"@{user.username}" if user and user.username else "—"
    status_str = sponsor.status.value if hasattr(sponsor.status, "value") else str(sponsor.status)

    text = (
        f"💼 <b>SPONSOR #{sponsor.id}</b>\n\n"
        f"━━━━━━ PROFILE ━━━━━━\n"
        f"👤 User: <code>{sponsor.user_id}</code> {username}\n"
        f"📌 Status: <b>{status_str}</b>\n\n"
        f"━━━━━━ WALLET ━━━━━━\n"
        f"💰 Available: <b>{fmt_usdt(sponsor.available_balance)} USDT</b>\n"
        f"🔒 Reserved:  <b>{fmt_usdt(sponsor.reserved_balance)} USDT</b>\n"
        f"💸 Total Spent: <b>{fmt_usdt(sponsor.total_spent)} USDT</b>\n"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=sponsor_action_keyboard(sponsor.id, status_str),
    )


async def _admin_view_campaign(query, campaign_id: int) -> None:
    async with get_session() as session:
        from models.campaign import Campaign

        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            await query.edit_message_text("❌ Campaign not found.")
            return

    status_str = campaign.status.value if hasattr(campaign.status, "value") else str(campaign.status)

    text = (
        f"📋 <b>CAMPAIGN #{campaign.id}</b>\n\n"
        f"📝 Title: {campaign.title}\n"
        f"📌 Status: <b>{status_str}</b>\n"
        f"💰 Budget: <b>{fmt_usdt(campaign.total_budget)} USDT</b>\n"
        f"💸 Spent: <b>{fmt_usdt(campaign.spent_budget)} USDT</b>\n"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=campaign_action_keyboard(campaign_id, status_str),
    )


async def _admin_view_withdrawal(query, withdrawal_id: int) -> None:
    async with get_session() as session:
        from models.withdrawal import Withdrawal

        wd = await session.get(Withdrawal, withdrawal_id)
        if not wd:
            await query.edit_message_text("❌ Withdrawal not found.")
            return

    status_str = wd.status.value if hasattr(wd.status, "value") else str(wd.status)

    text = (
        f"💳 <b>WITHDRAWAL #{wd.id}</b>\n\n"
        f"👤 User: <code>{wd.user_id}</code>\n"
        f"💰 Amount: <b>{fmt_usdt(wd.amount)} USDT</b>\n"
        f"📌 Status: <b>{status_str}</b>\n"
        f"🏦 Wallet: <code>{getattr(wd, 'wallet_address', '—')}</code>\n"
    )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=withdrawal_action_keyboard(withdrawal_id),
    )


async def _admin_banned_list(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.user import User, UserStatus

        result = await session.execute(
            select(User).where(User.status == UserStatus.BANNED).limit(20)
        )
        banned = result.scalars().all()

    lines = ["🚫 <b>BANNED USERS</b>\n"]
    for u in banned:
        lines.append(f"• <code>{u.id}</code> @{u.username or '—'}")
    if not banned:
        lines.append("No banned users.")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_flagged_list(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.user import User, UserStatus

        result = await session.execute(
            select(User).where(User.status == UserStatus.FLAGGED).limit(20)
        )
        flagged = result.scalars().all()

    lines = ["⚠️ <b>FLAGGED USERS</b>\n"]
    for u in flagged:
        lines.append(f"• <code>{u.id}</code> @{u.username or '—'} — score {u.fraud_score}")
    if not flagged:
        lines.append("No flagged users.")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )

# ══════════════════════════════════════════════════════════════════
# Admin: Manually add balance to sponsor account
# ══════════════════════════════════════════════════════════════════

async def _admin_sponsor_add_balance_prompt(
    query, context: ContextTypes.DEFAULT_TYPE, sponsor_id: int
) -> None:
    """Step 1 — show sponsor info and ask for amount."""
    async with get_session() as session:
        from models.sponsor import Sponsor
        from models.user import User

        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            await query.edit_message_text("❌ Sponsor not found.")
            return
        user = await session.get(User, sponsor.user_id)

    username = f"@{user.username}" if user and user.username else f"ID:{sponsor.user_id}"
    status_str = sponsor.status.value if hasattr(sponsor.status, "value") else str(sponsor.status)

    context.user_data["admin_add_balance_sponsor_id"] = sponsor_id
    context.user_data["admin_add_balance_sponsor_name"] = username
    context.user_data["admin_add_balance_current"] = str(sponsor.available_balance)

    await query.edit_message_text(
        f"💳 <b>ADD BALANCE — Sponsor #{sponsor_id}</b>\n\n"
        f"👤 Sponsor: <b>{username}</b>\n"
        f"📌 Status: <b>{status_str}</b>\n"
        f"💰 Current Balance: <b>{fmt_usdt(sponsor.available_balance)} USDT</b>\n\n"
        f"Send the amount to add (USDT).\n"
        f"Example: <code>10.5</code>\n\n"
        f"Send /cancel to abort.",
        parse_mode="HTML",
    )
    context.user_data["admin_awaiting_sponsor_balance"] = True


async def admin_sponsor_balance_input_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Step 2 — receive amount text and ask for confirmation.
    Early-exits for non-admins and when no awaiting state is set.
    """
    if not settings.is_admin(update.effective_user.id):
        return  # Not an admin — let next handler deal with it

    # Only handle when specifically waiting for sponsor balance input
    if not context.user_data.get("admin_awaiting_sponsor_balance"):
        return  # Not in this flow — pass through

    text = update.message.text.strip()

    if text.lower() in ("/cancel", "cancel"):
        context.user_data.pop("admin_awaiting_sponsor_balance", None)
        context.user_data.pop("admin_add_balance_sponsor_id", None)
        await update.message.reply_text(
            "❌ Cancelled.",
            reply_markup=admin_main_reply_keyboard(),
        )
        return

    try:
        from decimal import Decimal, InvalidOperation
        amount = Decimal(text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Invalid amount. Send a positive number like <code>5.00</code>",
            parse_mode="HTML",
        )
        return

    sponsor_id = context.user_data.get("admin_add_balance_sponsor_id")
    username = context.user_data.get("admin_add_balance_sponsor_name", "")
    current = context.user_data.get("admin_add_balance_current", "0")

    context.user_data["admin_add_balance_amount"] = str(amount)
    context.user_data["admin_awaiting_sponsor_balance"] = False
    context.user_data["admin_awaiting_sponsor_balance_confirm"] = True

    await update.message.reply_text(
        f"⚠️ <b>CONFIRM BALANCE ADD</b>\n\n"
        f"Sponsor #{sponsor_id} ({username})\n"
        f"Current balance: <b>{current} USDT</b>\n"
        f"Adding: <b>{fmt_usdt(amount)} USDT</b>\n"
        f"New balance: <b>{fmt_usdt(Decimal(current) + amount)} USDT</b>\n\n"
        f"Confirm?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"admin:sponsor_balance_confirm:{sponsor_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"admin:sponsor_view:{sponsor_id}"),
            ]
        ]),
    )


async def _admin_sponsor_balance_confirm(
    query, context: ContextTypes.DEFAULT_TYPE, sponsor_id: int, admin_id: int
) -> None:
    """Step 3 — execute the credit after admin confirms."""
    import hashlib
    import uuid
    from decimal import Decimal

    amount_str = context.user_data.pop("admin_add_balance_amount", None)
    context.user_data.pop("admin_awaiting_sponsor_balance_confirm", None)
    context.user_data.pop("admin_add_balance_sponsor_id", None)
    context.user_data.pop("admin_add_balance_sponsor_name", None)
    context.user_data.pop("admin_add_balance_current", None)

    if not amount_str:
        await query.edit_message_text("❌ Session expired. Start over from the sponsor panel.")
        return

    amount = Decimal(amount_str)

    idempotency_key = hashlib.sha256(
        f"admin_credit:{sponsor_id}:{amount}:{uuid.uuid4()}:{settings.SECRET_SALT}".encode()
    ).hexdigest()

    try:
        async with get_session() as session:
            async with session.begin():
                from services.ledger_service import LedgerService
                from models.transaction import TransactionType
                from models.sponsor import Sponsor
                from models.user import User

                tx = await LedgerService.credit_sponsor(
                    session=session,
                    sponsor_id=sponsor_id,
                    amount=amount,
                    tx_type=TransactionType.ADMIN_CREDIT,
                    idempotency_key=idempotency_key,
                    description=f"Manual credit by admin {admin_id}",
                )

                # Fetch updated info for confirmation message
                sponsor = await session.get(Sponsor, sponsor_id)
                user = await session.get(User, sponsor.user_id) if sponsor else None

                # Audit log
                from models.audit_log import AuditLog
                log_entry = AuditLog(
                    admin_id=admin_id,
                    action="sponsor_manual_credit",
                    target_type="sponsor",
                    target_id=sponsor_id,
                    new_value={
                        "amount": str(amount),
                        "tx_id": tx.id,
                        "new_balance": str(sponsor.available_balance) if sponsor else "?",
                    },
                )
                session.add(log_entry)

        username = f"@{user.username}" if user and user.username else f"ID:{sponsor.user_id if sponsor else '?'}"
        new_balance = sponsor.available_balance if sponsor else Decimal("0")

        log.info(
            "Admin manually credited sponsor",
            admin_id=admin_id,
            sponsor_id=sponsor_id,
            amount=str(amount),
            tx_id=tx.id,
        )

        # Notify the sponsor
        if user:
            import asyncio
            asyncio.create_task(
                _send_sponsor_balance_notification(user.id, amount, new_balance)
            )

        await query.edit_message_text(
            f"✅ <b>Balance Added Successfully</b>\n\n"
            f"Sponsor #{sponsor_id} ({username})\n"
            f"Added: <b>{fmt_usdt(amount)} USDT</b>\n"
            f"New Balance: <b>{fmt_usdt(new_balance)} USDT</b>\n"
            f"TX #{tx.id}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 View Sponsor", callback_data=f"admin:sponsor_view:{sponsor_id}")]
            ]),
        )

    except Exception as e:
        log.error("Admin sponsor credit failed", error=str(e), sponsor_id=sponsor_id)
        await query.edit_message_text(
            f"❌ Failed to add balance: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


async def _send_sponsor_balance_notification(user_id: int, amount, new_balance) -> None:
    """Notify sponsor that admin added balance to their account."""
    from services.notification_service import NotificationService
    from services.notification_service import _send
    await _send(
        user_id,
        f"💳 <b>Balance Added</b>\n\n"
        f"An admin has added <b>{fmt_usdt(amount)} USDT</b> to your sponsor account.\n"
        f"💰 New Balance: <b>{fmt_usdt(new_balance)} USDT</b>",
    )
