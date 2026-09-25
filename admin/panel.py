"""
Admin Panel — main entry point and callback router.
All handlers verify admin authorization on every call.
"""
import asyncio
import structlog
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import settings
from database import get_session
from keyboards.admin_keyboards import (
    admin_main_reply_keyboard,
    admin_back_reply_keyboard,
    admin_cancel_reply_keyboard,
    user_action_keyboard,
    user_detail_keyboard,
    campaign_action_keyboard,
    withdrawal_action_keyboard,
    sponsor_action_keyboard,
    deposit_action_keyboard,
    force_join_manage_keyboard,
    force_join_confirm_delete_keyboard,
)
from utils.decimal_utils import fmt_usdt
from utils.time_utils import fmt_datetime

log = structlog.get_logger(__name__)


def _require_admin(user_id: int) -> bool:
    return settings.is_admin(user_id)


def _enum_str(v) -> str:
    if v is None:
        return "—"
    return v.value if hasattr(v, "value") else str(v)


async def _safe_edit(query, text: str, **kwargs) -> None:
    """edit_message_text — silently handles not-modified and edit-not-found."""
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        msg = str(e).lower()
        if "not modified" in msg:
            return
        if "message to edit not found" in msg or "can't be edited" in msg:
            try:
                await query.message.reply_text(text, **kwargs)
            except Exception:
                pass
            return
        raise


# ══════════════════════════════════════════════════════════════════
# Entry point — /admin
# ══════════════════════════════════════════════════════════════════

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛡 <b>ADMIN PANEL</b>\n\nSelect an option:",
        parse_mode="HTML",
        reply_markup=admin_main_reply_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════
# Central callback router — all "admin:" callbacks
# ══════════════════════════════════════════════════════════════════

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if not _require_admin(user.id):
        await query.answer("❌ Not authorized.", show_alert=True)
        return

    await query.answer()
    data = query.data
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    # ── Top-level views ──
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
    elif action == "audit":
        await _admin_audit(query)
    elif action == "broadcast":
        await _admin_broadcast_prompt(query, context)
    elif action == "force_join":
        await _admin_force_join_list(query)

    # ── Force Join branches ──
    elif action == "fj_add":
        await _admin_fj_add_prompt(query, context)
    elif action == "fj_view" and len(parts) > 2:
        await _admin_fj_view(query, int(parts[2]))
    elif action == "fj_delete" and len(parts) > 2:
        await _admin_fj_delete_prompt(query, int(parts[2]))
    elif action == "fj_delete_confirm" and len(parts) > 2:
        await _admin_fj_delete_confirm(query, int(parts[2]), user.id)

    # ── Views of specific items ──
    elif action == "user_view" and len(parts) > 2:
        await _admin_view_user(query, int(parts[2]))
    elif action == "sponsor_view" and len(parts) > 2:
        await _admin_view_sponsor(query, int(parts[2]))
    elif action == "campaign_view" and len(parts) > 2:
        await _admin_view_campaign(query, int(parts[2]))
    elif action == "campaign_delete" and len(parts) > 2:
        await _admin_delete_campaign(query, int(parts[2]), user.id)
    elif action == "wd_view" and len(parts) > 2:
        await _admin_view_withdrawal(query, int(parts[2]))
    elif action == "deposit_view" and len(parts) > 2:
        await _admin_view_deposit(query, int(parts[2]))
    elif action == "banned":
        await _admin_banned_list(query)
    elif action == "flagged":
        await _admin_flagged_list(query)
    elif action == "user_search":
        await _admin_user_search_prompt(query, context)

    # ── Actions ──
    elif action == "back":
        await _safe_edit(query, "🛡 <b>ADMIN PANEL</b>", parse_mode="HTML")
    elif action.startswith("ban") and len(parts) > 2 and not action.startswith("banned"):
        await _admin_ban_user(query, int(parts[2]), user.id)
    elif action.startswith("unban") and len(parts) > 2:
        await _admin_unban_user(query, int(parts[2]), user.id)
    elif action.startswith("user_balance") and len(parts) > 2:
        await _admin_user_balance_prompt(query, context, int(parts[2]))
    elif action.startswith("user_balance_confirm") and len(parts) > 2:
        await _admin_user_balance_confirm(query, context, int(parts[2]), user.id)
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
    elif action.startswith("sponsor_activate") and len(parts) > 2:
        await _admin_activate_sponsor(query, int(parts[2]), user.id)
    elif action.startswith("sponsor_add_balance") and len(parts) > 2:
        await _admin_sponsor_balance_prompt(query, context, int(parts[2]))
    elif action.startswith("sponsor_balance_confirm") and len(parts) > 2:
        await _admin_sponsor_balance_confirm(query, context, int(parts[2]), user.id)
    elif action.startswith("deposit_approve") and len(parts) > 2:
        await _admin_approve_deposit(query, int(parts[2]), user.id)
    elif action.startswith("deposit_reject") and len(parts) > 2:
        await _admin_reject_deposit(query, int(parts[2]), user.id)
    elif action.startswith("wd_approve") and len(parts) > 2:
        await _admin_approve_withdrawal(query, int(parts[2]), user.id)
    elif action.startswith("wd_reject") and len(parts) > 2:
        await _admin_reject_withdrawal(query, int(parts[2]), user.id)
    else:
        await _safe_edit(
            query,
            f"❓ Unknown action: <code>{data}</code>",
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════════════════════
# Reply keyboard handlers
# ══════════════════════════════════════════════════════════════════

async def admin_panel_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🛡 <b>ADMIN PANEL</b>\n\nSelect an option:",
        parse_mode="HTML",
        reply_markup=admin_main_reply_keyboard(),
    )


async def admin_force_join_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📢 Force Join button — show manage list."""
    if not _require_admin(update.effective_user.id):
        return

    async with get_session() as session:
        from sqlalchemy import select
        from models.force_join import ForceJoinChannel

        result = await session.execute(
            select(ForceJoinChannel).order_by(ForceJoinChannel.id.asc())
        )
        rows = [
            {
                "id": c.id,
                "chat_id": c.chat_id,
                "username": c.username,
                "title": getattr(c, "title", None),
                "invite_url": c.invite_url,
                "is_active": c.is_active,
            }
            for c in result.scalars().all()
        ]

    if not rows:
        text = (
            "📢 <b>FORCE JOIN CHANNELS</b>\n\n"
            "No channels configured.\n\n"
            "Tap ➕ Add Channel to add one."
        )
    else:
        text = (
            f"📢 <b>FORCE JOIN CHANNELS</b>\n\n"
            f"Total: <b>{len(rows)}</b>\n\n"
            f"Tap a channel to view or delete."
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=force_join_manage_keyboard(rows),
    )


async def admin_users_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        pending_rows = [
            {"id": c.id, "title": c.title}
            for c in pending.scalars().all()
        ]

    buttons = []
    for c in pending_rows:
        buttons.append([InlineKeyboardButton(
            f"⏳ #{c['id']}: {c['title'][:30]}",
            callback_data=f"admin:campaign_view:{c['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    status_lines = "\n".join(
        f"{s.value}: <b>{counts[s]:,}</b>" for s in CampaignStatus
    )

    await update.message.reply_text(
        f"📋 <b>CAMPAIGNS</b>\n\n{status_lines}\n\n"
        + ("⏳ <b>Pending Approval:</b>" if pending_rows else "✅ No pending campaigns"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_sponsors_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💼 Sponsors — show ALL sponsors grouped by status."""
    if not _require_admin(update.effective_user.id):
        return

    async with get_session() as session:
        from sqlalchemy import select
        from models.sponsor import Sponsor

        result = await session.execute(
            select(Sponsor).order_by(Sponsor.id.asc()).limit(40)
        )
        all_sponsors = [
            {
                "id": s.id,
                "user_id": s.user_id,
                "status": _enum_str(s.status),
                "available": s.available_balance,
            }
            for s in result.scalars().all()
        ]

    icons = {
        "PENDING": "⏳",
        "APPROVED": "✅",
        "SUSPENDED": "🚫",
        "REJECTED": "❌",
    }

    # Group order: PENDING, APPROVED, SUSPENDED, REJECTED
    order = ["PENDING", "APPROVED", "SUSPENDED", "REJECTED"]
    by_status = {k: [] for k in order}
    others = []

    for s in all_sponsors:
        if s["status"] in by_status:
            by_status[s["status"]].append(s)
        else:
            others.append(s)

    buttons = []
    for status_key in order:
        for s in by_status[status_key]:
            icon = icons.get(status_key, "•")
            buttons.append([InlineKeyboardButton(
                f"{icon} #{s['id']} — user {s['user_id']} — {fmt_usdt(s['available'])} USDT",
                callback_data=f"admin:sponsor_view:{s['id']}"
            )])

    for s in others:
        buttons.append([InlineKeyboardButton(
            f"• #{s['id']} — user {s['user_id']} — {s['status']}",
            callback_data=f"admin:sponsor_view:{s['id']}"
        )])

    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    counts = {k: len(by_status[k]) for k in order}
    total = len(all_sponsors)

    await update.message.reply_text(
        f"💼 <b>SPONSORS</b>\n\n"
        f"⏳ Pending: <b>{counts['PENDING']}</b>\n"
        f"✅ Approved: <b>{counts['APPROVED']}</b>\n"
        f"🚫 Suspended: <b>{counts['SUSPENDED']}</b>\n"
        f"❌ Rejected: <b>{counts['REJECTED']}</b>\n\n"
        f"Total: <b>{total}</b>\n"
        + ("\nTap a sponsor to manage." if total else "No sponsors yet."),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_deposits_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💰 Deposits — stats + pending list."""
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

        pending_result = await session.execute(
            select(Deposit)
            .where(Deposit.status == DepositStatus.PENDING)
            .order_by(Deposit.created_at.asc())
            .limit(10)
        )
        rows = [
            {"id": d.id, "amount": d.amount, "tx_hash": d.tx_hash}
            for d in pending_result.scalars().all()
        ]

    buttons = []
    for d in rows:
        short_hash = f"{d['tx_hash'][:8]}…{d['tx_hash'][-6:]}" if d["tx_hash"] else "—"
        buttons.append([InlineKeyboardButton(
            f"⏳ #{d['id']} — {fmt_usdt(d['amount'])} USDT — {short_hash}",
            callback_data=f"admin:deposit_view:{d['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    await update.message.reply_text(
        f"💰 <b>DEPOSITS</b>\n\n"
        f"Total confirmed: <b>{fmt_usdt(total_confirmed)} USDT</b>\n"
        f"Pending verification: <b>{pending_count}</b>\n\n"
        + ("⏳ <b>Pending Deposits:</b>" if rows else "✅ No pending deposits"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_withdrawals_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        rows = [
            {"id": w.id, "amount": w.amount}
            for w in pending.scalars().all()
        ]

    buttons = []
    for w in rows:
        buttons.append([InlineKeyboardButton(
            f"💵 #{w['id']} — {fmt_usdt(w['amount'])} USDT",
            callback_data=f"admin:wd_view:{w['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:back")])

    await update.message.reply_text(
        f"💳 <b>WITHDRAWALS</b>\n\nPending: <b>{len(rows)}</b>",
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
        "⚠️ This cannot be undone.\n\n"
        "Send <code>/cancel</code> to abort.",
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
        rows = [{"id": u.id, "username": u.username} for u in result.scalars().all()]

    lines = ["🚫 <b>BANNED USERS</b>\n"]
    for u in rows:
        lines.append(f"• <code>{u['id']}</code> @{u['username'] or '—'}")
    if not rows:
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
        rows = [
            {
                "admin_id": e.admin_id,
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "created_at": e.created_at,
            }
            for e in result.scalars().all()
        ]

    lines = ["📜 <b>AUDIT LOGS (Last 10)</b>\n"]
    for e in rows:
        lines.append(
            f"• [{fmt_datetime(e['created_at'])}] "
            f"Admin {e['admin_id']}: {e['action']} on {e['target_type']} #{e['target_id']}"
        )
    if not rows:
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
    await update.message.reply_text(
        "Admin panel closed.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def admin_cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _require_admin(update.effective_user.id):
        return
    context.user_data.pop("admin_awaiting_broadcast", None)
    context.user_data.pop("admin_awaiting_sponsor_balance", None)
    context.user_data.pop("admin_awaiting_user_search", None)
    context.user_data.pop("admin_awaiting_user_balance", None)
    context.user_data.pop("admin_awaiting_fj_add", None)
    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=admin_main_reply_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════
# Central free-text input dispatcher
# ══════════════════════════════════════════════════════════════════

async def admin_text_input_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route admin free-text input based on user_data state."""
    if not update.message or not update.message.text:
        return
    if not _require_admin(update.effective_user.id):
        return

    text = update.message.text.strip()

    if text.lower() in ("/cancel", "cancel"):
        if any(k.startswith("admin_awaiting_") for k in context.user_data):
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Cancelled.", reply_markup=admin_main_reply_keyboard()
            )
            return

    if context.user_data.get("admin_awaiting_sponsor_balance"):
        await _handle_sponsor_balance_input(update, context, text)
        return

    if context.user_data.get("admin_awaiting_user_balance"):
        await _handle_user_balance_input(update, context, text)
        return

    if context.user_data.get("admin_awaiting_user_search"):
        await _handle_user_search_input(update, context, text)
        return

    if context.user_data.get("admin_awaiting_broadcast"):
        await _handle_broadcast_input(update, context, text)
        return

    if context.user_data.get("admin_awaiting_fj_add"):
        await _handle_fj_add_input(update, context, text)
        return


# ══════════════════════════════════════════════════════════════════
# Internal renderers
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

    await _safe_edit(
        query,
        f"👥 <b>USERS</b>\n\n"
        f"Total: <b>{total:,}</b>\n"
        f"Active: <b>{active:,}</b>\n"
        f"Flagged: <b>{flagged:,}</b>\n"
        f"Banned: <b>{banned:,}</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _admin_user_search_prompt(query, context) -> None:
    context.user_data["admin_awaiting_user_search"] = True
    await _safe_edit(
        query,
        "🔍 <b>SEARCH USER</b>\n\n"
        "Send the user ID (e.g. <code>6566849366</code>) or <code>@username</code>.\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Users", callback_data="admin:users")]
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
        pending_rows = [
            {"id": c.id, "title": c.title}
            for c in pending.scalars().all()
        ]

    buttons = []
    for c in pending_rows:
        buttons.append([InlineKeyboardButton(
            f"⏳ #{c['id']}: {c['title'][:30]}",
            callback_data=f"admin:campaign_view:{c['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    status_lines = "\n".join(
        f"{s.value}: <b>{counts[s]:,}</b>" for s in CampaignStatus
    )

    await _safe_edit(
        query,
        f"📋 <b>CAMPAIGNS</b>\n\n{status_lines}\n\n"
        + ("⏳ <b>Pending Approval:</b>" if pending_rows else "✅ No pending campaigns"),
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
        rows = [
            {"id": w.id, "amount": w.amount}
            for w in pending.scalars().all()
        ]

    buttons = []
    for w in rows:
        buttons.append([InlineKeyboardButton(
            f"💵 #{w['id']} — {fmt_usdt(w['amount'])} USDT",
            callback_data=f"admin:wd_view:{w['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    await _safe_edit(
        query,
        f"💳 <b>WITHDRAWALS</b>\n\nPending: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _admin_sponsors(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.sponsor import Sponsor

        result = await session.execute(
            select(Sponsor).order_by(Sponsor.id.asc()).limit(40)
        )
        all_sponsors = [
            {
                "id": s.id,
                "user_id": s.user_id,
                "status": _enum_str(s.status),
                "available": s.available_balance,
            }
            for s in result.scalars().all()
        ]

    icons = {
        "PENDING": "⏳",
        "APPROVED": "✅",
        "SUSPENDED": "🚫",
        "REJECTED": "❌",
    }
    order = ["PENDING", "APPROVED", "SUSPENDED", "REJECTED"]
    by_status = {k: [] for k in order}
    for s in all_sponsors:
        if s["status"] in by_status:
            by_status[s["status"]].append(s)

    buttons = []
    for key in order:
        for s in by_status[key]:
            buttons.append([InlineKeyboardButton(
                f"{icons.get(key, '•')} #{s['id']} (user {s['user_id']})",
                callback_data=f"admin:sponsor_view:{s['id']}"
            )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    counts = {k: len(by_status[k]) for k in order}

    await _safe_edit(
        query,
        f"💼 <b>SPONSORS</b>\n\n"
        f"⏳ Pending: <b>{counts['PENDING']}</b>\n"
        f"✅ Approved: <b>{counts['APPROVED']}</b>\n"
        f"🚫 Suspended: <b>{counts['SUSPENDED']}</b>\n"
        f"❌ Rejected: <b>{counts['REJECTED']}</b>",
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

        pending_result = await session.execute(
            select(Deposit)
            .where(Deposit.status == DepositStatus.PENDING)
            .order_by(Deposit.created_at.asc())
            .limit(10)
        )
        rows = [
            {"id": d.id, "amount": d.amount, "tx_hash": d.tx_hash}
            for d in pending_result.scalars().all()
        ]

    buttons = []
    for d in rows:
        short_hash = f"{d['tx_hash'][:8]}…{d['tx_hash'][-6:]}" if d["tx_hash"] else "—"
        buttons.append([InlineKeyboardButton(
            f"⏳ #{d['id']} — {fmt_usdt(d['amount'])} USDT — {short_hash}",
            callback_data=f"admin:deposit_view:{d['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:back")])

    await _safe_edit(
        query,
        f"💰 <b>DEPOSITS</b>\n\n"
        f"Total confirmed: <b>{fmt_usdt(total_confirmed)} USDT</b>\n"
        f"Pending verification: <b>{pending_count}</b>\n\n"
        + ("⏳ <b>Pending Deposits:</b>" if rows else "✅ No pending deposits"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
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

    await _safe_edit(
        query,
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

    await _safe_edit(
        query,
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
    await _safe_edit(
        query,
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
        rows = [
            {
                "admin_id": e.admin_id,
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "created_at": e.created_at,
            }
            for e in result.scalars().all()
        ]

    lines = ["📜 <b>AUDIT LOGS (Last 5)</b>\n"]
    for e in rows:
        lines.append(
            f"• [{fmt_datetime(e['created_at'])}] "
            f"Admin {e['admin_id']}: {e['action']} on {e['target_type']} #{e['target_id']}"
        )
    if not rows:
        lines.append("No audit logs yet.")

    await _safe_edit(
        query,
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


async def _admin_broadcast_prompt(query, context) -> None:
    context.user_data["admin_awaiting_broadcast"] = True
    await _safe_edit(
        query,
        "📢 <b>BROADCAST</b>\n\n"
        "Send your message to broadcast to ALL users.\n\n"
        "⚠️ This cannot be undone.\n\n"
        "Send <code>/cancel</code> to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:back")]
        ]),
    )


# ══════════════════════════════════════════════════════════════════
# View handlers
# ══════════════════════════════════════════════════════════════════

async def _admin_view_user(query, user_id: int) -> None:
    async with get_session() as session:
        from models.user import User

        u = await session.get(User, user_id)
        if not u:
            await _safe_edit(query, "❌ User not found.")
            return

        data = {
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "status": _enum_str(u.status),
            "fraud_score": u.fraud_score,
            "balance": u.balance,
            "total_earned": u.total_earned,
            "total_withdrawn": u.total_withdrawn,
            "tasks_completed": u.tasks_completed,
            "referral_code": u.referral_code,
            "referrer_id": u.referrer_id,
            "bsc_wallet": u.bsc_wallet,
            "joined_at": u.joined_at,
            "last_active": u.last_active,
        }

    text = (
        f"👤 <b>USER #{data['id']}</b>\n\n"
        f"━━━━━━ PROFILE ━━━━━━\n"
        f"📛 Name: {data['first_name'] or '—'} {data['last_name'] or ''}\n"
        f"🔗 Username: @{data['username'] or '—'}\n"
        f"📌 Status: <b>{data['status']}</b>\n"
        f"🛡 Fraud score: <b>{data['fraud_score']}</b>\n"
        f"📅 Joined: {fmt_datetime(data['joined_at']) if data['joined_at'] else '—'}\n"
        f"🕐 Last active: {fmt_datetime(data['last_active']) if data['last_active'] else '—'}\n\n"
        f"━━━━━━ BALANCES ━━━━━━\n"
        f"💰 Balance: <b>{fmt_usdt(data['balance'])} USDT</b>\n"
        f"📈 Total earned: <b>{fmt_usdt(data['total_earned'])} USDT</b>\n"
        f"📉 Total withdrawn: <b>{fmt_usdt(data['total_withdrawn'])} USDT</b>\n"
        f"✅ Tasks completed: <b>{data['tasks_completed']}</b>\n\n"
        f"━━━━━━ REFERRAL ━━━━━━\n"
        f"🎁 Code: <code>{data['referral_code'] or '—'}</code>\n"
        f"👤 Referrer: <code>{data['referrer_id'] or '—'}</code>\n\n"
        f"━━━━━━ WALLET ━━━━━━\n"
        f"🏦 BSC: <code>{data['bsc_wallet'] or 'not set'}</code>"
    )

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=user_detail_keyboard(user_id, data["status"]),
    )


async def _admin_view_sponsor(query, sponsor_id: int) -> None:
    async with get_session() as session:
        from models.sponsor import Sponsor
        from models.user import User

        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            await _safe_edit(query, "❌ Sponsor not found.")
            return

        data = {
            "id": sponsor.id,
            "user_id": sponsor.user_id,
            "status": _enum_str(sponsor.status),
            "available": sponsor.available_balance,
            "reserved": sponsor.reserved_balance,
            "spent": sponsor.total_spent,
            "deposited": getattr(sponsor, "total_deposited", None),
        }

        u = await session.get(User, sponsor.user_id)
        username = f"@{u.username}" if u and u.username else "—"

    text = (
        f"💼 <b>SPONSOR #{data['id']}</b>\n\n"
        f"━━━━━━ PROFILE ━━━━━━\n"
        f"👤 User: <code>{data['user_id']}</code> {username}\n"
        f"📌 Status: <b>{data['status']}</b>\n\n"
        f"━━━━━━ WALLET ━━━━━━\n"
        f"💰 Available: <b>{fmt_usdt(data['available'])} USDT</b>\n"
        f"🔒 Reserved:  <b>{fmt_usdt(data['reserved'])} USDT</b>\n"
        f"💸 Total Spent: <b>{fmt_usdt(data['spent'])} USDT</b>\n"
    )
    if data["deposited"] is not None:
        text += f"📥 Total Deposited: <b>{fmt_usdt(data['deposited'])} USDT</b>\n"

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=sponsor_action_keyboard(sponsor_id, data["status"]),
    )


async def _admin_view_campaign(query, campaign_id: int) -> None:
    async with get_session() as session:
        from models.campaign import Campaign

        c = await session.get(Campaign, campaign_id)
        if not c:
            await _safe_edit(query, "❌ Campaign not found.")
            return

        data = {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "status": _enum_str(c.status),
            "task_type": _enum_str(c.task_type),
            "telegram_username": c.telegram_username,
            "invite_url": c.invite_url,
            "reward_per_user": c.reward_per_user,
            "completion_limit": c.completion_limit,
            "completed_count": c.completed_count,
            "total_budget": c.total_budget,
            "reserved_budget": c.reserved_budget,
            "spent_budget": c.spent_budget,
            "view_count": c.view_count,
            "click_count": c.click_count,
            "expires_at": c.expires_at,
            "created_at": c.created_at,
        }

    text = (
        f"📋 <b>CAMPAIGN #{data['id']}</b>\n\n"
        f"📝 Title: {data['title']}\n"
        f"📌 Status: <b>{data['status']}</b>\n"
        f"🎯 Type: {data['task_type']}\n"
        f"🔗 Target: @{data['telegram_username'] or '—'}\n"
        f"⏱ Expires: {fmt_datetime(data['expires_at']) if data['expires_at'] else '—'}\n\n"
        f"━━━━━━ BUDGET ━━━━━━\n"
        f"💰 Total: <b>{fmt_usdt(data['total_budget'])} USDT</b>\n"
        f"🔒 Reserved: <b>{fmt_usdt(data['reserved_budget'])} USDT</b>\n"
        f"💸 Spent: <b>{fmt_usdt(data['spent_budget'])} USDT</b>\n"
        f"💵 Reward/user: <b>{fmt_usdt(data['reward_per_user'])} USDT</b>\n\n"
        f"━━━━━━ PROGRESS ━━━━━━\n"
        f"✅ Completed: <b>{data['completed_count']} / {data['completion_limit']}</b>\n"
        f"👁 Views: <b>{data['view_count']}</b>\n"
        f"🔗 Clicks: <b>{data['click_count']}</b>"
    )

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=campaign_action_keyboard(campaign_id, data["status"]),
    )


async def _admin_view_withdrawal(query, withdrawal_id: int) -> None:
    async with get_session() as session:
        from models.withdrawal import Withdrawal

        w = await session.get(Withdrawal, withdrawal_id)
        if not w:
            await _safe_edit(query, "❌ Withdrawal not found.")
            return

        data = {
            "id": w.id,
            "user_id": w.user_id,
            "amount": w.amount,
            "status": _enum_str(w.status),
            "wallet_address": getattr(w, "wallet_address", None),
            "created_at": getattr(w, "created_at", None),
        }

    text = (
        f"💳 <b>WITHDRAWAL #{data['id']}</b>\n\n"
        f"👤 User: <code>{data['user_id']}</code>\n"
        f"💰 Amount: <b>{fmt_usdt(data['amount'])} USDT</b>\n"
        f"📌 Status: <b>{data['status']}</b>\n"
        f"🏦 Wallet: <code>{data['wallet_address'] or '—'}</code>\n"
        f"📅 Created: {fmt_datetime(data['created_at']) if data['created_at'] else '—'}"
    )

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=withdrawal_action_keyboard(withdrawal_id),
    )


async def _admin_view_deposit(query, deposit_id: int) -> None:
    async with get_session() as session:
        from models.deposit import Deposit
        from models.sponsor import Sponsor
        from models.user import User

        d = await session.get(Deposit, deposit_id)
        if not d:
            await _safe_edit(query, "❌ Deposit not found.")
            return

        data = {
            "id": d.id,
            "sponsor_id": d.sponsor_id,
            "amount": d.amount,
            "status": _enum_str(d.status),
            "network": d.network,
            "tx_hash": d.tx_hash,
            "from_address": d.from_address,
            "confirmations": d.confirmations,
            "created_at": d.created_at,
            "credited_at": d.credited_at,
        }

        sponsor = await session.get(Sponsor, d.sponsor_id)
        sponsor_user_id = sponsor.user_id if sponsor else None
        sponsor_available = sponsor.available_balance if sponsor else None
        sponsor_status = _enum_str(sponsor.status) if sponsor else "—"

        username = "—"
        if sponsor_user_id:
            u = await session.get(User, sponsor_user_id)
            if u and u.username:
                username = f"@{u.username}"

    text = (
        f"💰 <b>DEPOSIT #{data['id']}</b>\n\n"
        f"━━━━━━ DETAILS ━━━━━━\n"
        f"📌 Status: <b>{data['status']}</b>\n"
        f"💵 Amount: <b>{fmt_usdt(data['amount'])} USDT</b>\n"
        f"🌐 Network: <b>{data['network']}</b>\n"
        f"🔗 TX Hash:\n<code>{data['tx_hash']}</code>\n"
        f"📤 From: <code>{data['from_address'] or '—'}</code>\n"
        f"✅ Confirmations: <b>{data['confirmations']}</b>\n"
        f"📅 Created: {fmt_datetime(data['created_at']) if data['created_at'] else '—'}\n"
        f"💳 Credited: {fmt_datetime(data['credited_at']) if data['credited_at'] else '—'}\n\n"
        f"━━━━━━ SPONSOR ━━━━━━\n"
        f"👤 User: <code>{sponsor_user_id or '—'}</code> {username}\n"
        f"📌 Status: <b>{sponsor_status}</b>\n"
        f"💰 Current balance: <b>{fmt_usdt(sponsor_available) if sponsor_available is not None else '—'} USDT</b>"
    )

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=deposit_action_keyboard(deposit_id, data["status"]),
    )


async def _admin_banned_list(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.user import User, UserStatus

        result = await session.execute(
            select(User).where(User.status == UserStatus.BANNED).limit(20)
        )
        rows = [{"id": u.id, "username": u.username} for u in result.scalars().all()]

    lines = ["🚫 <b>BANNED USERS</b>\n"]
    for u in rows:
        lines.append(f"• <code>{u['id']}</code> @{u['username'] or '—'}")
    if not rows:
        lines.append("No banned users.")

    await _safe_edit(
        query,
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
        rows = [
            {"id": u.id, "username": u.username, "score": u.fraud_score}
            for u in result.scalars().all()
        ]

    lines = ["⚠️ <b>FLAGGED USERS</b>\n"]
    for u in rows:
        lines.append(f"• <code>{u['id']}</code> @{u['username'] or '—'} — score {u['score']}")
    if not rows:
        lines.append("No flagged users.")

    await _safe_edit(
        query,
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:back")]
        ]),
    )


# ═══════════════════════════════════════════════════# ══════════════════════════════════════════════════════════════════
# Action handlers
# ══════════════════════════════════════════════════════════════════

async def _admin_ban_user(query, target_user_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.user import User, UserStatus
            from models.audit_log import AuditLog

            user = await session.get(User, target_user_id)
            if not user:
                await _safe_edit(query, "❌ User not found.")
                return

            old_status = _enum_str(user.status)
            user.status = UserStatus.BANNED

            session.add(AuditLog(
                admin_id=admin_id,
                action="BAN_USER",
                target_type="user",
                target_id=target_user_id,
                old_value={"status": old_status},
                new_value={"status": "BANNED"},
            ))

    await _safe_edit(
        query,
        f"✅ User <code>{target_user_id}</code> has been banned.",
        parse_mode="HTML",
        reply_markup=user_detail_keyboard(target_user_id, "BANNED"),
    )


async def _admin_unban_user(query, target_user_id: int, admin_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from models.user import User, UserStatus
            from models.audit_log import AuditLog

            user = await session.get(User, target_user_id)
            if not user:
                await _safe_edit(query, "❌ User not found.")
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

    await _safe_edit(
        query,
        f"✅ User <code>{target_user_id}</code> has been unbanned.",
        parse_mode="HTML",
        reply_markup=user_detail_keyboard(target_user_id, "ACTIVE"),
    )


async def _admin_approve_campaign(query, campaign_id: int, admin_id: int) -> None:
    try:
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

        await _safe_edit(
            query,
            f"✅ Campaign #{campaign_id} approved and pending funding.",
        )
    except Exception as e:
        log.exception("Approve campaign failed", campaign_id=campaign_id)
        await _safe_edit(
            query,
            f"❌ Failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
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

    await _safe_edit(query, f"❌ Campaign #{campaign_id} rejected.")


async def _admin_pause_campaign(query, campaign_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from services.campaign_service import CampaignService
                await CampaignService.pause_campaign(session, campaign_id, admin_id)
        await _safe_edit(query, f"⏸ Campaign #{campaign_id} paused.")
    except Exception as e:
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_resume_campaign(query, campaign_id: int, admin_id: int) -> None:
    try:
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

        await _safe_edit(query, f"▶️ Campaign #{campaign_id} resumed.")
    except Exception as e:
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_approve_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from services.sponsor_service import SponsorService
                await SponsorService.approve_sponsor(session, sponsor_id, admin_id)
        await _safe_edit(query, f"✅ Sponsor #{sponsor_id} approved.")
    except Exception as e:
        log.exception("Approve sponsor failed", sponsor_id=sponsor_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_reject_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from models.sponsor import Sponsor, SponsorStatus
                from models.audit_log import AuditLog

                sponsor = await session.get(Sponsor, sponsor_id)
                if not sponsor:
                    await _safe_edit(query, "❌ Sponsor not found.")
                    return

                old_status = _enum_str(sponsor.status)
                # Prefer REJECTED; fall back to SUSPENDED if enum lacks REJECTED
                target = getattr(SponsorStatus, "REJECTED", None) or \
                         getattr(SponsorStatus, "SUSPENDED", None)
                if target is not None:
                    sponsor.status = target

                sponsor_user_id = sponsor.user_id

                session.add(AuditLog(
                    admin_id=admin_id,
                    action="REJECT_SPONSOR",
                    target_type="sponsor",
                    target_id=sponsor_id,
                    old_value={"status": old_status},
                    new_value={"status": "REJECTED"},
                ))

        # Notify sponsor
        from services.notification_service import NotificationService
        asyncio.create_task(
            NotificationService.send_to_user(
                sponsor_user_id,
                "❌ <b>Sponsor Application Rejected</b>\n\n"
                "Your sponsor application was not approved.\n\n"
                "Contact support for more details.",
            )
        )

        await _safe_edit(
            query,
            f"❌ Sponsor #{sponsor_id} rejected.",
            reply_markup=sponsor_action_keyboard(sponsor_id, "REJECTED"),
        )
    except Exception as e:
        log.exception("Reject sponsor failed", sponsor_id=sponsor_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_suspend_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from models.sponsor import Sponsor, SponsorStatus
                from models.audit_log import AuditLog

                sponsor = await session.get(Sponsor, sponsor_id)
                if not sponsor:
                    await _safe_edit(query, "❌ Sponsor not found.")
                    return

                old_status = _enum_str(sponsor.status)
                target = getattr(SponsorStatus, "SUSPENDED", None) or \
                         getattr(SponsorStatus, "PENDING")
                sponsor.status = target

                sponsor_user_id = sponsor.user_id

                session.add(AuditLog(
                    admin_id=admin_id,
                    action="SUSPEND_SPONSOR",
                    target_type="sponsor",
                    target_id=sponsor_id,
                    old_value={"status": old_status},
                    new_value={"status": "SUSPENDED"},
                ))

        # Notify sponsor
        from services.notification_service import NotificationService
        asyncio.create_task(
            NotificationService.send_to_user(
                sponsor_user_id,
                "🚫 <b>Sponsor Account Suspended</b>\n\n"
                "Your sponsor account has been suspended by an admin.\n\n"
                "You cannot create or fund new campaigns right now.\n"
                "Active campaigns remain running.\n\n"
                "Contact support if you believe this is a mistake.",
            )
        )

        await _safe_edit(
            query,
            f"🚫 Sponsor #{sponsor_id} suspended.",
            reply_markup=sponsor_action_keyboard(sponsor_id, "SUSPENDED"),
        )
    except Exception as e:
        log.exception("Suspend sponsor failed", sponsor_id=sponsor_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_activate_sponsor(query, sponsor_id: int, admin_id: int) -> None:
    """Re-activate a suspended or rejected sponsor — sets status to APPROVED."""
    try:
        async with get_session() as session:
            async with session.begin():
                from models.sponsor import Sponsor, SponsorStatus
                from models.audit_log import AuditLog

                sponsor = await session.get(Sponsor, sponsor_id)
                if not sponsor:
                    await _safe_edit(query, "❌ Sponsor not found.")
                    return

                old_status = _enum_str(sponsor.status)

                if old_status not in ("SUSPENDED", "REJECTED", "PENDING"):
                    await _safe_edit(
                        query,
                        f"⚠️ Sponsor is already <b>{old_status}</b> — no change needed.",
                        parse_mode="HTML",
                        reply_markup=sponsor_action_keyboard(sponsor_id, old_status),
                    )
                    return

                sponsor.status = SponsorStatus.APPROVED
                sponsor_user_id = sponsor.user_id

                session.add(AuditLog(
                    admin_id=admin_id,
                    action="ACTIVATE_SPONSOR",
                    target_type="sponsor",
                    target_id=sponsor_id,
                    old_value={"status": old_status},
                    new_value={"status": "APPROVED"},
                ))

        # Notify the sponsor
        from services.notification_service import NotificationService
        asyncio.create_task(
            NotificationService.send_to_user(
                sponsor_user_id,
                "✅ <b>Sponsor Account Reactivated</b>\n\n"
                "Your sponsor account has been re-activated.\n"
                "You can now create campaigns again.\n\n"
                "Open /sponsor to continue.",
            )
        )

        await _safe_edit(
            query,
            f"✅ <b>Sponsor #{sponsor_id} Reactivated</b>\n\n"
            f"Status: <b>{old_status}</b> → <b>APPROVED</b>",
            parse_mode="HTML",
            reply_markup=sponsor_action_keyboard(sponsor_id, "APPROVED"),
        )
    except Exception as e:
        log.exception("Activate sponsor failed", sponsor_id=sponsor_id)
        await _safe_edit(
            query,
            f"❌ Failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


async def _admin_approve_withdrawal(query, withdrawal_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from services.withdrawal_service import WithdrawalService
                success = await WithdrawalService.process_withdrawal(session, withdrawal_id)

        if success:
            await _safe_edit(query, f"✅ Withdrawal #{withdrawal_id} processed successfully.")
        else:
            await _safe_edit(query, f"❌ Withdrawal #{withdrawal_id} failed. User refunded.")
    except Exception as e:
        log.exception("Approve withdrawal failed", withdrawal_id=withdrawal_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_reject_withdrawal(query, withdrawal_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from models.withdrawal import Withdrawal, WithdrawalStatus
                from services.withdrawal_service import WithdrawalService

                wd = await session.get(Withdrawal, withdrawal_id)
                if wd and wd.status == WithdrawalStatus.PENDING:
                    await WithdrawalService._refund_failed_withdrawal(
                        session, wd, "Rejected by admin"
                    )
        await _safe_edit(query, f"❌ Withdrawal #{withdrawal_id} rejected. User refunded.")
    except Exception as e:
        log.exception("Reject withdrawal failed", withdrawal_id=withdrawal_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")
# ══════════════════════════════════════════════════════════════════
# Deposit approve / reject
# ══════════════════════════════════════════════════════════════════

async def _admin_approve_deposit(query, deposit_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from models.deposit import Deposit, DepositStatus
                from models.sponsor import Sponsor
                from models.audit_log import AuditLog

                deposit = await session.get(Deposit, deposit_id)
                if not deposit:
                    await _safe_edit(query, "❌ Deposit not found.")
                    return

                if deposit.status != DepositStatus.PENDING:
                    await _safe_edit(
                        query,
                        f"❌ Deposit is already <b>{_enum_str(deposit.status)}</b>.",
                        parse_mode="HTML",
                    )
                    return

                sponsor = await session.get(Sponsor, deposit.sponsor_id)
                if not sponsor:
                    await _safe_edit(query, "❌ Sponsor record not found.")
                    return

                amount = deposit.amount
                old_balance = sponsor.available_balance
                new_balance = old_balance + amount
                sponsor_user_id = sponsor.user_id

                sponsor.available_balance = new_balance
                if getattr(sponsor, "total_deposited", None) is not None:
                    sponsor.total_deposited = sponsor.total_deposited + amount

                deposit.status = DepositStatus.CONFIRMED
                deposit.credited_at = datetime.now(tz=timezone.utc)

                session.add(AuditLog(
                    admin_id=admin_id,
                    action="APPROVE_DEPOSIT",
                    target_type="deposit",
                    target_id=deposit_id,
                    old_value={"status": "PENDING", "sponsor_balance": str(old_balance)},
                    new_value={
                        "status": "CONFIRMED",
                        "credited": str(amount),
                        "sponsor_balance": str(new_balance),
                    },
                ))

        await _safe_edit(
            query,
            f"✅ <b>Deposit #{deposit_id} Approved</b>\n\n"
            f"Credited: <b>{fmt_usdt(amount)} USDT</b>\n"
            f"Sponsor new balance: <b>{fmt_usdt(new_balance)} USDT</b>",
            parse_mode="HTML",
        )

        asyncio.create_task(_notify_user(
            sponsor_user_id,
            f"✅ <b>Deposit Confirmed</b>\n\n"
            f"Amount: <b>{fmt_usdt(amount)} USDT</b>\n"
            f"New balance: <b>{fmt_usdt(new_balance)} USDT</b>",
        ))
    except Exception as e:
        log.exception("Approve deposit failed", deposit_id=deposit_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")


async def _admin_reject_deposit(query, deposit_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from models.deposit import Deposit, DepositStatus
                from models.audit_log import AuditLog

                deposit = await session.get(Deposit, deposit_id)
                if not deposit:
                    await _safe_edit(query, "❌ Deposit not found.")
                    return

                if deposit.status != DepositStatus.PENDING:
                    await _safe_edit(
                        query,
                        f"❌ Deposit is already <b>{_enum_str(deposit.status)}</b>.",
                        parse_mode="HTML",
                    )
                    return

                deposit.status = DepositStatus.FAILED
                session.add(AuditLog(
                    admin_id=admin_id,
                    action="REJECT_DEPOSIT",
                    target_type="deposit",
                    target_id=deposit_id,
                    old_value={"status": "PENDING"},
                    new_value={"status": "FAILED"},
                ))

        await _safe_edit(
            query,
            f"❌ <b>Deposit #{deposit_id} Rejected</b>\n\n"
            f"Marked as FAILED. No balance was credited.",
            parse_mode="HTML",
        )
    except Exception as e:
        log.exception("Reject deposit failed", deposit_id=deposit_id)
        await _safe_edit(query, f"❌ {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════
# Sponsor balance add
# ══════════════════════════════════════════════════════════════════

async def _admin_sponsor_balance_prompt(query, context, sponsor_id: int) -> None:
    async with get_session() as session:
        from models.sponsor import Sponsor

        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            await _safe_edit(query, "❌ Sponsor not found.")
            return

        context.user_data["admin_awaiting_sponsor_balance"] = True
        context.user_data["admin_sponsor_id"] = sponsor_id
        context.user_data["admin_sponsor_current"] = str(sponsor.available_balance)

    await _safe_edit(
        query,
        f"💰 <b>ADD BALANCE — Sponsor #{sponsor_id}</b>\n\n"
        f"Current balance: <b>{fmt_usdt(Decimal(context.user_data['admin_sponsor_current']))} USDT</b>\n\n"
        f"Send the amount in USDT (e.g. <code>50</code>):\n\n"
        f"Send /cancel to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data=f"admin:sponsor_view:{sponsor_id}")]
        ]),
    )


async def _handle_sponsor_balance_input(update, context, text: str) -> None:
    try:
        amount = Decimal(text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Invalid amount. Send a positive number like <code>50</code>.",
            parse_mode="HTML",
        )
        return

    sponsor_id = context.user_data.get("admin_sponsor_id")
    if not sponsor_id:
        context.user_data.pop("admin_awaiting_sponsor_balance", None)
        return

    context.user_data["admin_awaiting_sponsor_balance"] = False

    try:
        async with get_session() as session:
            async with session.begin():
                from models.sponsor import Sponsor
                from models.audit_log import AuditLog

                sponsor = await session.get(Sponsor, sponsor_id)
                if not sponsor:
                    await update.message.reply_text("❌ Sponsor not found.")
                    context.user_data.pop("admin_awaiting_sponsor_balance", None)
                    return

                old = sponsor.available_balance
                new = old + amount
                sponsor_user_id = sponsor.user_id

                sponsor.available_balance = new
                if getattr(sponsor, "total_deposited", None) is not None:
                    sponsor.total_deposited = sponsor.total_deposited + amount

                session.add(AuditLog(
                    admin_id=update.effective_user.id,
                    action="SPONSOR_ADD_BALANCE",
                    target_type="sponsor",
                    target_id=sponsor_id,
                    old_value={"available_balance": str(old)},
                    new_value={"available_balance": str(new), "added": str(amount)},
                ))

        context.user_data.pop("admin_sponsor_id", None)
        context.user_data.pop("admin_sponsor_current", None)

        await update.message.reply_text(
            f"✅ <b>Balance Added</b>\n\n"
            f"Sponsor #{sponsor_id}\n"
            f"Added: <b>{fmt_usdt(amount)} USDT</b>\n"
            f"New balance: <b>{fmt_usdt(new)} USDT</b>",
            parse_mode="HTML",
            reply_markup=admin_main_reply_keyboard(),
        )

        asyncio.create_task(_notify_user(
            sponsor_user_id,
            f"💳 <b>Balance Added</b>\n\n"
            f"Admin added <b>{fmt_usdt(amount)} USDT</b> to your sponsor wallet.\n"
            f"New balance: <b>{fmt_usdt(new)} USDT</b>",
        ))
    except Exception as e:
        log.exception("Sponsor balance add failed", sponsor_id=sponsor_id)
        await update.message.reply_text(
            f"❌ Failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


async def _admin_sponsor_balance_confirm(query, context, sponsor_id: int, admin_id: int) -> None:
    await _safe_edit(query, "⚠️ Use the current flow (send amount directly).")


# ══════════════════════════════════════════════════════════════════
# User search
# ══════════════════════════════════════════════════════════════════

async def _handle_user_search_input(update, context, text: str) -> None:
    context.user_data.pop("admin_awaiting_user_search", None)

    target_id = None
    if text.startswith("@") or not text.isdigit():
        async with get_session() as session:
            from sqlalchemy import select
            from models.user import User

            uname = text.lstrip("@")
            result = await session.execute(
                select(User).where(User.username == uname).limit(1)
            )
            u = result.scalar_one_or_none()
            if u:
                target_id = u.id
    else:
        target_id = int(text)

    if not target_id:
        await update.message.reply_text(
            "❌ User not found.",
            reply_markup=admin_main_reply_keyboard(),
        )
        return

    class _FakeQuery:
        def __init__(self, message):
            self.message = message
            self.data = None
        async def edit_message_text(self, text, **kwargs):
            await self.message.reply_text(text, **kwargs)
        async def answer(self, *a, **kw):
            pass

    fake = _FakeQuery(update.message)
    await _admin_view_user(fake, target_id)


# ══════════════════════════════════════════════════════════════════
# User balance adjust
# ══════════════════════════════════════════════════════════════════

async def _admin_user_balance_prompt(query, context, user_id: int) -> None:
    context.user_data["admin_awaiting_user_balance"] = True
    context.user_data["admin_user_balance_id"] = user_id

    async with get_session() as session:
        from models.user import User
        u = await session.get(User, user_id)
        if not u:
            await _safe_edit(query, "❌ User not found.")
            return
        current = u.balance

    await _safe_edit(
        query,
        f"💰 <b>ADJUST BALANCE — User #{user_id}</b>\n\n"
        f"Current balance: <b>{fmt_usdt(current)} USDT</b>\n\n"
        f"Send the amount to ADD (positive) or REMOVE (negative, e.g. <code>-5</code>):\n\n"
        f"Send /cancel to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data=f"admin:user_view:{user_id}")]
        ]),
    )


async def _handle_user_balance_input(update, context, text: str) -> None:
    try:
        amount = Decimal(text)
        if amount == 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Invalid amount. Send a number like <code>5</code> or <code>-5</code>.",
            parse_mode="HTML",
        )
        return

    user_id = context.user_data.get("admin_user_balance_id")
    if not user_id:
        context.user_data.pop("admin_awaiting_user_balance", None)
        return

    context.user_data.pop("admin_awaiting_user_balance", None)
    context.user_data.pop("admin_user_balance_id", None)

    try:
        async with get_session() as session:
            async with session.begin():
                from models.user import User
                from models.audit_log import AuditLog

                u = await session.get(User, user_id)
                if not u:
                    await update.message.reply_text("❌ User not found.")
                    return

                old = u.balance
                new = old + amount
                if new < 0:
                    await update.message.reply_text(
                        f"❌ Cannot reduce below zero. Current: {fmt_usdt(old)} USDT"
                    )
                    return

                u.balance = new

                session.add(AuditLog(
                    admin_id=update.effective_user.id,
                    action="USER_ADJUST_BALANCE",
                    target_type="user",
                    target_id=user_id,
                    old_value={"balance": str(old)},
                    new_value={"balance": str(new), "delta": str(amount)},
                ))

        await update.message.reply_text(
            f"✅ <b>Balance Adjusted</b>\n\n"
            f"User #{user_id}\n"
            f"Delta: <b>{'+' if amount > 0 else ''}{fmt_usdt(amount)} USDT</b>\n"
            f"New balance: <b>{fmt_usdt(new)} USDT</b>",
            parse_mode="HTML",
            reply_markup=admin_main_reply_keyboard(),
        )
    except Exception as e:
        log.exception("User balance adjust failed", user_id=user_id)
        await update.message.reply_text(
            f"❌ Failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


async def _admin_user_balance_confirm(query, context, user_id: int, admin_id: int) -> None:
    await _safe_edit(query, "⚠️ Use the current flow (send amount directly).")


# ══════════════════════════════════════════════════════════════════
# Broadcast
# ══════════════════════════════════════════════════════════════════

async def _handle_broadcast_input(update, context, text: str) -> None:
    context.user_data.pop("admin_awaiting_broadcast", None)

    async with get_session() as session:
        from sqlalchemy import select
        from models.user import User, UserStatus

        result = await session.execute(
            select(User.id).where(User.status != UserStatus.BANNED)
        )
        user_ids = [row[0] for row in result.all()]

    if not user_ids:
        await update.message.reply_text("❌ No users to broadcast to.")
        return

    await update.message.reply_text(
        f"📢 Broadcasting to <b>{len(user_ids):,}</b> users...",
        parse_mode="HTML",
    )

    asyncio.create_task(_do_broadcast(update.get_bot(), user_ids, text))


async def _do_broadcast(bot, user_ids, text: str) -> None:
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    log.info("Broadcast finished", sent=sent, failed=failed)


# ══════════════════════════════════════════════════════════════════
# Notification helper
# ══════════════════════════════════════════════════════════════════

async def _notify_user(user_id: int, text: str) -> None:
    """Best-effort send via NotificationService."""
    try:
        from services.notification_service import NotificationService
        for name in ("send_to_user", "send_message", "notify_user"):
            fn = getattr(NotificationService, name, None)
            if callable(fn):
                await fn(user_id, text)
                return
        log.warning("NotificationService has no known user-send method")
    except Exception:
        log.exception("Failed to notify user", user_id=user_id)


# ══════════════════════════════════════════════════════════════════
# Admin campaign delete (force)
# ══════════════════════════════════════════════════════════════════

async def _admin_delete_campaign(query, campaign_id: int, admin_id: int) -> None:
    """Admin force-delete a campaign."""
    try:
        async with get_session() as session:
            async with session.begin():
                from services.campaign_service import CampaignService
                from models.audit_log import AuditLog

                summary = await CampaignService.delete_campaign(
                    session=session,
                    campaign_id=campaign_id,
                    actor_id=admin_id,
                    actor_is_admin=True,
                )

                session.add(AuditLog(
                    admin_id=admin_id,
                    action="DELETE_CAMPAIGN",
                    target_type="campaign",
                    target_id=campaign_id,
                    old_value={"title": summary.get("title", ""),
                               "status": summary.get("status", "")},
                ))

        released = summary.get("released", Decimal("0"))
        released_line = ""
        if released and released > Decimal("0"):
            released_line = f"\n💰 Released to sponsor: <b>{fmt_usdt(released)} USDT</b>"

        await _safe_edit(
            query,
            f"✅ <b>Campaign #{campaign_id} Deleted</b>\n"
            f"📝 {summary.get('title', '')}"
            f"{released_line}",
            parse_mode="HTML",
        )
    except Exception as e:
        log.exception("Admin delete campaign failed", campaign_id=campaign_id)
        await _safe_edit(
            query,
            f"❌ Delete failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


# ══════════════════════════════════════════════════════════════════
# Force Join channel management
# ══════════════════════════════════════════════════════════════════

async def _admin_force_join_list(query) -> None:
    async with get_session() as session:
        from sqlalchemy import select
        from models.force_join import ForceJoinChannel

        result = await session.execute(
            select(ForceJoinChannel).order_by(ForceJoinChannel.id.asc())
        )
        rows = [
            {
                "id": c.id,
                "chat_id": c.chat_id,
                "username": c.username,
                "title": getattr(c, "title", None),
                "invite_url": c.invite_url,
                "is_active": c.is_active,
            }
            for c in result.scalars().all()
        ]

    if not rows:
        text = (
            "📢 <b>FORCE JOIN CHANNELS</b>\n\n"
            "No channels configured.\n\n"
            "Users can freely use the bot."
        )
    else:
        text = (
            f"📢 <b>FORCE JOIN CHANNELS</b>\n\n"
            f"Total: <b>{len(rows)}</b>\n\n"
            f"Tap a channel to view or delete."
        )

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=force_join_manage_keyboard(rows),
    )


async def _admin_fj_add_prompt(query, context) -> None:
    context.user_data["admin_awaiting_fj_add"] = True
    await _safe_edit(
        query,
        "➕ <b>ADD FORCE JOIN CHANNEL</b>\n\n"
        "Send the channel's <b>@username</b> or <b>numeric chat ID</b>.\n\n"
        "Examples:\n"
        "<code>@MyChannel</code>\n"
        "<code>-1001234567890</code>\n\n"
        "⚠️ Make sure the bot is <b>admin</b> in that channel.\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="admin:force_join")]
        ]),
    )


async def _handle_fj_add_input(update, context, text: str) -> None:
    context.user_data.pop("admin_awaiting_fj_add", None)

    raw = text.strip()
    chat_ref = None

    if raw.startswith("-100") or raw.lstrip("-").isdigit():
        try:
            chat_ref = int(raw)
        except ValueError:
            await update.message.reply_text("❌ Invalid chat ID.")
            return
    elif raw.startswith("@") or raw.startswith("https://t.me/"):
        chat_ref = raw
    else:
        chat_ref = f"@{raw}"

    bot = update.get_bot()

    try:
        chat = await bot.get_chat(chat_ref)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Cannot access chat.\n\n"
            f"Error: <code>{str(e)[:200]}</code>\n\n"
            f"Make sure the bot is an <b>admin</b> in that channel.",
            parse_mode="HTML",
        )
        return

    chat_id = chat.id
    username = chat.username
    title = chat.title or username or str(chat_id)
    invite_url = f"https://t.me/{username}" if username else None

    try:
        async with get_session() as session:
            async with session.begin():
                from sqlalchemy import select
                from models.force_join import ForceJoinChannel
                from models.audit_log import AuditLog

                existing = await session.execute(
                    select(ForceJoinChannel).where(ForceJoinChannel.chat_id == chat_id)
                )
                if existing.scalar_one_or_none():
                    await update.message.reply_text(
                        f"⚠️ Channel already added: <b>{title}</b>",
                        parse_mode="HTML",
                    )
                    return

                ch = ForceJoinChannel(
                    chat_id=chat_id,
                    username=username,
                    invite_url=invite_url,
                    is_active=True,
                )
                session.add(ch)
                await session.flush()
                new_id = ch.id

                session.add(AuditLog(
                    admin_id=update.effective_user.id,
                    action="ADD_FORCE_JOIN",
                    target_type="force_join",
                    target_id=new_id,
                    new_value={
                        "chat_id": str(chat_id),
                        "username": username,
                        "title": title,
                    },
                ))

        await update.message.reply_text(
            f"✅ <b>Force Join Channel Added</b>\n\n"
            f"📢 <b>{title}</b>\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"🔗 @{username or '—'}\n\n"
            f"Users will now be required to join before using the bot.",
            parse_mode="HTML",
            reply_markup=admin_main_reply_keyboard(),
        )
    except Exception as e:
        log.exception("Add force join channel failed")
        await update.message.reply_text(
            f"❌ Failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )


async def _admin_fj_view(query, channel_id: int) -> None:
    async with get_session() as session:
        from models.force_join import ForceJoinChannel
        ch = await session.get(ForceJoinChannel, channel_id)
        if not ch:
            await _safe_edit(query, "❌ Channel not found.")
            return

        data = {
            "id": ch.id,
            "chat_id": ch.chat_id,
            "username": ch.username,
            "invite_url": ch.invite_url,
            "is_active": ch.is_active,
            "created_at": ch.created_at,
        }

    text = (
        f"📢 <b>FORCE JOIN CHANNEL #{data['id']}</b>\n\n"
        f"🆔 Chat ID: <code>{data['chat_id']}</code>\n"
        f"🔗 Username: @{data['username'] or '—'}\n"
        f"🌐 Invite URL: {data['invite_url'] or '—'}\n"
        f"📌 Status: <b>{'✅ Active' if data['is_active'] else '⏸ Inactive'}</b>\n"
        f"📅 Added: {fmt_datetime(data['created_at']) if data['created_at'] else '—'}\n"
    )

    await _safe_edit(
        query,
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🗑 Delete Channel",
                callback_data=f"admin:fj_delete:{data['id']}",
            )],
            [InlineKeyboardButton("🔙 Back", callback_data="admin:force_join")],
        ]),
    )


async def _admin_fj_delete_prompt(query, channel_id: int) -> None:
    async with get_session() as session:
        from models.force_join import ForceJoinChannel
        ch = await session.get(ForceJoinChannel, channel_id)
        if not ch:
            await _safe_edit(query, "❌ Channel not found.")
            return
        label = ch.username or str(ch.chat_id)

    await _safe_edit(
        query,
        f"🗑 <b>DELETE CHANNEL?</b>\n\n"
        f"📢 {label}\n\n"
        f"Users will no longer be forced to join this channel.\n\n"
        f"Are you sure?",
        parse_mode="HTML",
        reply_markup=force_join_confirm_delete_keyboard(channel_id),
    )


async def _admin_fj_delete_confirm(query, channel_id: int, admin_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from models.force_join import ForceJoinChannel
                from models.audit_log import AuditLog

                ch = await session.get(ForceJoinChannel, channel_id)
                if not ch:
                    await _safe_edit(query, "❌ Channel not found.")
                    return

                label = ch.username or str(ch.chat_id)
                chat_id_val = ch.chat_id
                username_val = ch.username
                await session.delete(ch)

                session.add(AuditLog(
                    admin_id=admin_id,
                    action="DELETE_FORCE_JOIN",
                    target_type="force_join",
                    target_id=channel_id,
                    old_value={"chat_id": str(chat_id_val), "username": username_val},
                ))

        await _safe_edit(
            query,
            f"✅ <b>Channel Deleted</b>\n\n📢 {label}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to List", callback_data="admin:force_join")]
            ]),
        )
    except Exception as e:
        log.exception("Delete force join channel failed", channel_id=channel_id)
        await _safe_edit(query, f"❌ Failed: <code>{str(e)[:200]}</code>", parse_mode="HTML")