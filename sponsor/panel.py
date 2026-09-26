"""
Sponsor Panel — campaign management and wallet for approved sponsors.
"""
import re
import structlog
from decimal import Decimal
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import get_session
from keyboards.sponsor_keyboards import (
    sponsor_main_reply_keyboard,
    sponsor_task_type_reply_keyboard,
    sponsor_duration_reply_keyboard,
    sponsor_cancel_reply_keyboard,
    sponsor_back_reply_keyboard,
    campaign_actions_keyboard,
    deposit_submitted_keyboard,
)
from utils.decimal_utils import fmt_usdt

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Channel input parsing
# ══════════════════════════════════════════════════════════════════

def _parse_channel_input(raw: str) -> dict:
    """
    Parse user input into channel reference. Supports:
      @username, username, https://t.me/username, t.me/username,
      -1001234567890 (numeric chat id),
      https://t.me/+abcDEF (private invite),
      https://t.me/joinchat/xyz
    Returns:
      {"username": str|None, "chat_id": int|None,
       "invite_url": str|None, "display": str}
    """
    s = (raw or "").strip()
    if not s:
        return {"username": None, "chat_id": None, "invite_url": None, "display": "—"}

    # Numeric chat_id
    if s.lstrip("-").isdigit():
        try:
            cid = int(s)
            return {"username": None, "chat_id": cid,
                    "invite_url": None, "display": str(cid)}
        except ValueError:
            pass

    # Strip scheme
    normalized = s
    if normalized.startswith("https://"):
        normalized = normalized[8:]
    elif normalized.startswith("http://"):
        normalized = normalized[7:]

    # Strip t.me / telegram.me
    for prefix in ("t.me/", "telegram.me/", "www.t.me/"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    # Strip query string
    normalized = normalized.split("?")[0].strip().rstrip("/")

    # Private invite — +code or joinchat/code
    if normalized.startswith("+"):
        code = normalized[1:]
        return {
            "username": None,
            "chat_id": None,
            "invite_url": f"https://t.me/+{code}",
            "display": f"private invite (+{code[:6]}…)",
        }
    if normalized.startswith("joinchat/"):
        code = normalized[len("joinchat/"):]
        return {
            "username": None,
            "chat_id": None,
            "invite_url": f"https://t.me/joinchat/{code}",
            "display": f"private invite ({code[:6]}…)",
        }

    # t.me/c/12345 → internal chat_id
    m = re.match(r"^c/(\d+)", normalized)
    if m:
        cid = -1000000000000 - int(m.group(1))
        return {"username": None, "chat_id": cid,
                "invite_url": None, "display": str(cid)}

    # Otherwise — treat as username
    username = normalized.lstrip("@").strip()

    if not username:
        return {"username": None, "chat_id": None, "invite_url": None, "display": "—"}

    return {
        "username": username,
        "chat_id": None,
        "invite_url": f"https://t.me/{username}",
        "display": f"@{username}",
    }


def _status_str(status) -> str:
    """Convert enum or str to uppercase string."""
    if hasattr(status, "value"):
        return str(status.value).upper()
    return str(status).upper()


def _status_icon(status) -> str:
    s = _status_str(status)
    return {
        "ACTIVE": "🟢",
        "PAUSED": "⏸",
        "COMPLETED": "✅",
        "PENDING": "⏳",
        "PENDING_FUNDING": "💳",
        "EXPIRED": "❌",
        "CANCELLED": "🚫",
        "DRAFT": "📝",
    }.get(s, "•")


async def _get_sponsor(session, user_id: int):
    from services.sponsor_service import SponsorService
    return await SponsorService.get_sponsor_by_user(session, user_id)


# # ══════════════════════════════════════════════════════════════════
# Entry point — /sponsor command
# ══════════════════════════════════════════════════════════════════

async def sponsor_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry — show sponsor panel or apply prompt."""
    user = update.effective_user
    message = update.message

    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)

        if not sponsor:
            await message.reply_text(
                "💼 <b>SPONSOR PANEL</b>\n\n"
                "You don't have a sponsor account yet.\n"
                "Apply to become a sponsor and run advertising campaigns.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [StyledButton(
                        "📩 Apply as Sponsor",
                        style="success",
                        callback_data="sponsor:apply",
                    )],
                ]),
            )
            return

        from models.sponsor import SponsorStatus
        if sponsor.status == SponsorStatus.PENDING:
            await message.reply_text(
                "⏳ Your sponsor application is under review.\n"
                "We'll notify you once approved."
            )
            return

        if sponsor.status != SponsorStatus.APPROVED:
            await message.reply_text(
                f"❌ Your sponsor account is {sponsor.status}. Contact support."
            )
            return

        stats = {
            "available": sponsor.available_balance,
            "reserved": sponsor.reserved_balance,
            "spent": sponsor.total_spent,
        }
        sponsor_id = sponsor.id

        from models.campaign import Campaign, CampaignStatus
        from sqlalchemy import select, func as sa_func

        active = (await session.execute(
            select(sa_func.count(Campaign.id)).where(
                Campaign.sponsor_id == sponsor_id,
                Campaign.status == CampaignStatus.ACTIVE
            )
        )).scalar()
        paused = (await session.execute(
            select(sa_func.count(Campaign.id)).where(
                Campaign.sponsor_id == sponsor_id,
                Campaign.status == CampaignStatus.PAUSED
            )
        )).scalar()
        completed = (await session.execute(
            select(sa_func.count(Campaign.id)).where(
                Campaign.sponsor_id == sponsor_id,
                Campaign.status == CampaignStatus.COMPLETED
            )
        )).scalar()

    text = (
        f"💼 <b>SPONSOR PANEL</b>\n\n"
        f"━━━━━━ YOUR WALLET ━━━━━━\n"
        f"💰 Available:    <b>{fmt_usdt(stats['available'])} USDT</b>\n"
        f"🔒 Reserved:     <b>{fmt_usdt(stats['reserved'])} USDT</b>\n"
        f"📊 Total Spent:  <b>{fmt_usdt(stats['spent'])} USDT</b>\n\n"
        f"━━━━━━ CAMPAIGNS ━━━━━━\n"
        f"🟢 Active:    <b>{active}</b>\n"
        f"⏸ Paused:    <b>{paused}</b>\n"
        f"✅ Completed: <b>{completed}</b>"
    )

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=sponsor_main_reply_keyboard(),
    )
# ══════════════════════════════════════════════════════════════════
# Reply keyboard handlers
# ══════════════════════════════════════════════════════════════════

async def sponsor_panel_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-show sponsor panel."""
    await sponsor_panel_handler(update, context)


async def sponsor_create_campaign_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """➕ Create Campaign — select task type."""
    context.user_data.clear()
    context.user_data["sponsor_step"] = "select_type"
    await update.message.reply_text(
        "📋 <b>CREATE CAMPAIGN</b>\n\nSelect task type:",
        parse_mode="HTML",
        reply_markup=sponsor_task_type_reply_keyboard(),
    )


async def sponsor_my_campaigns_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📋 My Campaigns — list sponsor campaigns."""
    user = update.effective_user
    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)
        if not sponsor:
            await update.message.reply_text("❌ No sponsor account.")
            return
        sponsor_id = sponsor.id

        from services.campaign_service import CampaignService
        campaigns = await CampaignService.get_sponsor_campaigns(session, sponsor_id)

        rows = [
            {
                "id": c.id,
                "title": c.title,
                "status": _status_str(c.status),
            }
            for c in campaigns[:10]
        ]

    if not rows:
        await update.message.reply_text(
            "📋 No campaigns yet. Create your first one!",
            reply_markup=sponsor_main_reply_keyboard(),
        )
        return

    buttons = []
    for c in rows:
        icon = {
            "ACTIVE": "🟢", "PAUSED": "⏸", "COMPLETED": "✅",
            "PENDING": "⏳", "PENDING_FUNDING": "💳",
            "EXPIRED": "❌", "CANCELLED": "🚫",
        }.get(c["status"], "•")
        buttons.append([InlineKeyboardButton(
            f"{icon} #{c['id']}: {c['title'][:25]}",
            callback_data=f"sponsor:campaign_detail:{c['id']}"
        )])

    await update.message.reply_text(
        "📋 <b>MY CAMPAIGNS</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def sponsor_deposit_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💰 Deposit USDT — show deposit info."""
    from config import settings
    context.user_data["sponsor_step"] = "enter_tx_hash"
    await update.message.reply_text(
        f"💰 <b>DEPOSIT USDT</b>\n\n"
        f"Send USDT (BEP-20) to:\n"
        f"<code>{settings.PAYOUT_WALLET_ADDRESS}</code>\n\n"
        f"🌐 Network: BNB Smart Chain (BSC)\n"
        f"📜 Contract: <code>{settings.USDT_CONTRACT_ADDRESS}</code>\n"
        f"💵 Minimum: {settings.SPONSOR_MIN_DEPOSIT} USDT\n"
        f"⏳ Confirmations: {settings.MIN_DEPOSIT_CONFIRMATIONS} blocks\n\n"
        f"After sending, reply with your <b>Transaction Hash</b> (0x...):",
        parse_mode="HTML",
        reply_markup=sponsor_cancel_reply_keyboard(),
    )


async def sponsor_analytics_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """📊 Analytics — overall sponsor analytics."""
    user = update.effective_user
    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)
        if not sponsor:
            await update.message.reply_text("❌ No sponsor account.")
            return
        sponsor_id = sponsor.id

        from services.sponsor_service import SponsorService
        info = await SponsorService.get_sponsor_wallet_info(session, sponsor_id)

    await update.message.reply_text(
        f"📊 <b>ANALYTICS</b>\n\n"
        f"💰 Available: <b>{fmt_usdt(info['available_balance'])} USDT</b>\n"
        f"🔒 Reserved: <b>{fmt_usdt(info['reserved_balance'])} USDT</b>\n"
        f"📊 Total Deposited: <b>{fmt_usdt(info['total_deposited'])} USDT</b>\n"
        f"💸 Total Spent: <b>{fmt_usdt(info['total_spent'])} USDT</b>",
        parse_mode="HTML",
        reply_markup=sponsor_back_reply_keyboard(),
    )


async def sponsor_wallet_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """💼 Wallet Info — deposit address and balances."""
    user = update.effective_user
    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)
        if not sponsor:
            await update.message.reply_text("❌ No sponsor account.")
            return
        sponsor_id = sponsor.id

        from services.sponsor_service import SponsorService
        info = await SponsorService.get_sponsor_wallet_info(session, sponsor_id)

    await update.message.reply_text(
        f"💼 <b>WALLET INFO</b>\n\n"
        f"💰 Available: <b>{fmt_usdt(info['available_balance'])} USDT</b>\n"
        f"🔒 Reserved: <b>{fmt_usdt(info['reserved_balance'])} USDT</b>\n"
        f"📊 Total Deposited: <b>{fmt_usdt(info['total_deposited'])} USDT</b>\n"
        f"💸 Total Spent: <b>{fmt_usdt(info['total_spent'])} USDT</b>\n\n"
        f"Deposit Address:\n<code>{info['deposit_address']}</code>\n"
        f"Network: {info['network']}\n"
        f"Minimum: {info['minimum_deposit']} USDT",
        parse_mode="HTML",
        reply_markup=sponsor_back_reply_keyboard(),
    )


async def sponsor_support_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🆘 Support — contact info."""
    from config import settings
    await update.message.reply_text(
        f"🆘 <b>SPONSOR SUPPORT</b>\n\n"
        f"For campaign and payment issues, contact: {settings.SUPPORT_USERNAME}",
        parse_mode="HTML",
        reply_markup=sponsor_back_reply_keyboard(),
    )


async def sponsor_back_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🔙 Back to Sponsor Panel."""
    context.user_data.pop("sponsor_step", None)
    context.user_data.pop("campaign_type", None)
    await sponsor_panel_handler(update, context)


async def sponsor_task_type_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Task type selected — ask for duration."""
    text = update.message.text
    type_map = {
        "📢 Channel Join": "CHANNEL_JOIN",
        "👥 Group Join": "GROUP_JOIN",
        
        "📢👥 Channel + Group": "CHANNEL_GROUP_JOIN",
    }
    task_type = type_map.get(text)
    if not task_type:
        return

    context.user_data["campaign_type"] = task_type
    context.user_data["sponsor_step"] = "select_duration"

    await update.message.reply_text(
        f"✅ Type: <b>{task_type}</b>\n\nNow choose campaign duration:",
        parse_mode="HTML",
        reply_markup=sponsor_duration_reply_keyboard(),
    )


async def sponsor_duration_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Duration selected — ask for channel username / link."""
    text = update.message.text
    days = {"1 Day": 1, "3 Days": 3, "7 Days": 7, "30 Days": 30}.get(text)
    if not days:
        return

    context.user_data["campaign_duration"] = days
    context.user_data["sponsor_step"] = "enter_username"

    await update.message.reply_text(
        f"✅ Duration: <b>{days} day(s)</b>\n\n"
        "Now send the Telegram channel/group link or username.\n\n"
        "<b>Any of these work:</b>\n"
        "• <code>@channelname</code>\n"
        "• <code>channelname</code>\n"
        "• <code>https://t.me/channelname</code>\n"
        "• <code>t.me/channelname</code>\n"
        "• <code>-1001234567890</code> (numeric chat ID)\n"
        "• <code>https://t.me/+inviteCode</code> (private invite)",
        parse_mode="HTML",
        reply_markup=sponsor_cancel_reply_keyboard(),
    )


async def sponsor_cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """❌ Cancel Sponsor."""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=sponsor_main_reply_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════
# Inline callback handler (per-item actions)
# ══════════════════════════════════════════════════════════════════

async def sponsor_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all sponsor: inline callbacks."""
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    data = query.data
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    # Apply flow — no sponsor needed
    if action == "apply":
        await _sponsor_apply(query, user.id)
        return

    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)
        sponsor_id = sponsor.id if sponsor else None

    if not sponsor:
        await query.edit_message_text("❌ No sponsor account found.")
        return

    if action == "campaigns":
        await _sponsor_list_campaigns(query, sponsor_id)

    elif action == "campaign_detail" and len(parts) > 2:
        await _sponsor_campaign_analytics(query, int(parts[2]))

    elif action == "delete_prompt" and len(parts) > 2:
        await _sponsor_delete_prompt(query, int(parts[2]), sponsor_id)

    elif action == "delete_confirm" and len(parts) > 2:
        await _sponsor_delete_confirm(query, int(parts[2]), sponsor_id)

    elif action == "fund" and len(parts) > 2:
        await _sponsor_fund_campaign(query, int(parts[2]), sponsor_id)

    elif action == "analytics" and len(parts) > 2:
        await _sponsor_campaign_analytics(query, int(parts[2]))

    elif action == "pause" and len(parts) > 2:
        await _sponsor_pause_campaign(query, int(parts[2]), sponsor_id)

    elif action == "resume" and len(parts) > 2:
        await _sponsor_resume_campaign(query, int(parts[2]), sponsor_id)

    elif action == "back":
        try:
            await query.edit_message_text(
                "💼 <b>SPONSOR PANEL</b>",
                parse_mode="HTML",
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise

    elif action == "cancel":
        context.user_data.clear()
        try:
            await query.edit_message_text("❌ Cancelled.")
        except BadRequest:
            pass


# ══════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════

async def _sponsor_apply(query, user_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from services.sponsor_service import SponsorService
            try:
                await SponsorService.apply_for_sponsor(session, user_id)
                await query.edit_message_text(
                    "✅ <b>Application Submitted!</b>\n\n"
                    "Our team will review your application and notify you once approved.",
                    parse_mode="HTML",
                )
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}")


async def _sponsor_list_campaigns(query, sponsor_id: int) -> None:
    async with get_session() as session:
        from services.campaign_service import CampaignService
        campaigns = await CampaignService.get_sponsor_campaigns(session, sponsor_id)

        rows = [
            {
                "id": c.id,
                "title": c.title,
                "status": _status_str(c.status),
            }
            for c in campaigns[:10]
        ]

    if not rows:
        try:
            await query.edit_message_text(
                "📋 No campaigns yet. Create your first one!",
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        return

    buttons = []
    for c in rows:
        icon = {
            "ACTIVE": "🟢", "PAUSED": "⏸", "COMPLETED": "✅",
            "PENDING": "⏳", "PENDING_FUNDING": "💳",
            "EXPIRED": "❌", "CANCELLED": "🚫",
        }.get(c["status"], "•")
        buttons.append([InlineKeyboardButton(
            f"{icon} #{c['id']}: {c['title'][:25]}",
            callback_data=f"sponsor:campaign_detail:{c['id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="sponsor:back")])

    try:
        await query.edit_message_text(
            "📋 <b>MY CAMPAIGNS</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def _sponsor_fund_campaign(query, campaign_id: int, sponsor_id: int) -> None:
    from services.campaign_service import CampaignValidationError
    try:
        async with get_session() as session:
            async with session.begin():
                from services.campaign_service import CampaignService
                campaign = await CampaignService.fund_campaign(
                    session, campaign_id, sponsor_id
                )
                total_budget = campaign.total_budget

        await query.edit_message_text(
            f"✅ Campaign <b>#{campaign_id}</b> funded and now ACTIVE!\n"
            f"Budget: <b>{fmt_usdt(total_budget)} USDT</b>",
            parse_mode="HTML",
        )
    except CampaignValidationError as e:
        await query.edit_message_text(f"❌ {e}")
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def _sponsor_pause_campaign(query, campaign_id: int, sponsor_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from services.campaign_service import CampaignService
                await CampaignService.pause_campaign(session, campaign_id, sponsor_id)
        await query.edit_message_text(f"⏸ Campaign #{campaign_id} paused.")
    except Exception as e:
        try:
            await query.edit_message_text(f"❌ {e}")
        except BadRequest:
            pass


async def _sponsor_resume_campaign(query, campaign_id: int, sponsor_id: int) -> None:
    try:
        async with get_session() as session:
            async with session.begin():
                from services.campaign_service import CampaignService
                await CampaignService.resume_campaign(session, campaign_id)
        await query.edit_message_text(f"▶️ Campaign #{campaign_id} resumed.")
    except Exception as e:
        try:
            await query.edit_message_text(f"❌ {e}")
        except BadRequest:
            pass


async def _sponsor_campaign_analytics(query, campaign_id: int) -> None:
    async with get_session() as session:
        from services.campaign_service import CampaignService
        data = await CampaignService.get_campaign_analytics(session, campaign_id)

    if not data:
        await query.edit_message_text("❌ Campaign not found.")
        return

    text = (
        f"📊 <b>CAMPAIGN ANALYTICS — #{data['id']}</b>\n\n"
        f"Title: {data['title']}\n\n"
        f"━━━━━━ PERFORMANCE ━━━━━━\n"
        f"👁 Views:           <b>{data['view_count']:,}</b>\n"
        f"🔗 Clicks (Join):   <b>{data['click_count']:,}</b>\n"
        f"✅ Verified:         <b>{data['completed_count']:,}</b>\n"
        f"❌ Failed Verify:    <b>{data['failed_verify_count']:,}</b>\n"
        f"⏭ Skipped:          <b>{data['skip_count']:,}</b>\n"
        f"📈 Completion Rate:  <b>{data['completion_rate']}%</b>\n\n"
        f"━━━━━━ BUDGET ━━━━━━\n"
        f"💰 Total:     <b>{fmt_usdt(data['total_budget'])} USDT</b>\n"
        f"💸 Spent:     <b>{fmt_usdt(data['spent_budget'])} USDT</b>\n"
        f"💰 Remaining: <b>{fmt_usdt(data['remaining_budget'])} USDT</b>"
    )

    try:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=campaign_actions_keyboard(campaign_id, data['status']),
        )
    except BadRequest as e:
        if "not modified" in str(e).lower():
            try:
                await query.answer("ℹ️ Already up to date")
            except Exception:
                pass
        else:
            raise


# ══════════════════════════════════════════════════════════════════
# Text input handler — for wizard steps
# ══════════════════════════════════════════════════════════════════

async def sponsor_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch text input during sponsor wizard flows."""
    step = context.user_data.get("sponsor_step")
    if not step:
        return

    text = (update.message.text or "").strip()

    # ── Campaign creation: enter_username ──
    if step == "enter_username":
        parsed = _parse_channel_input(text)

        if not (parsed["username"] or parsed["chat_id"] or parsed["invite_url"]):
            await update.message.reply_text(
                "❌ I couldn't understand that.\n\n"
                "Send one of:\n"
                "• <code>@channelname</code>\n"
                "• <code>https://t.me/channelname</code>\n"
                "• <code>-1001234567890</code>\n"
                "• <code>https://t.me/+inviteCode</code>",
                parse_mode="HTML",
                reply_markup=sponsor_cancel_reply_keyboard(),
            )
            return

        context.user_data["campaign_username"] = parsed["username"]
        context.user_data["campaign_chat_id"] = parsed["chat_id"]
        context.user_data["campaign_invite_url"] = parsed["invite_url"]
        context.user_data["sponsor_step"] = "enter_title"

        await update.message.reply_text(
            f"✅ Channel saved: <b>{parsed['display']}</b>\n\n"
            f"Now send a <b>title</b> for this campaign:",
            parse_mode="HTML",
            reply_markup=sponsor_cancel_reply_keyboard(),
        )
        return

    # ── Campaign creation: enter_title ──
    if step == "enter_title":
        context.user_data["campaign_title"] = text[:100]
        context.user_data["sponsor_step"] = "enter_reward"
        await update.message.reply_text(
            "✅ Title saved.\n\n"
            "Now send the <b>reward per task</b> in USDT (e.g. 0.05):",
            parse_mode="HTML",
            reply_markup=sponsor_cancel_reply_keyboard(),
        )
        return

    # ── Campaign creation: enter_reward ──
    if step == "enter_reward":
        try:
            reward = Decimal(text)
            if reward <= 0 or reward > Decimal("10"):
                raise ValueError
        except Exception:
            await update.message.reply_text(
                "❌ Invalid amount. Send a number between 0.001 and 10 (e.g. 0.05)"
            )
            return
        context.user_data["campaign_reward"] = str(reward)
        context.user_data["sponsor_step"] = "enter_budget"
        await update.message.reply_text(
            "✅ Reward saved.\n\n"
            "Now send the <b>total budget</b> in USDT (e.g. 100):",
            parse_mode="HTML",
            reply_markup=sponsor_cancel_reply_keyboard(),
        )
        return

    # ── Campaign creation: enter_budget → create in DB ──
    if step == "enter_budget":
        from datetime import datetime, timedelta, timezone

        try:
            budget = Decimal(text)
            if budget <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text("❌ Invalid budget. Send a number like 100")
            return

        user = update.effective_user
        reward = Decimal(context.user_data.get("campaign_reward", "0"))
        duration = int(context.user_data.get("campaign_duration", 1))
        task_type_str = context.user_data.get("campaign_type", "CHANNEL_JOIN")
        title = context.user_data.get("campaign_title", "Untitled")

        username = context.user_data.get("campaign_username")
        chat_id = context.user_data.get("campaign_chat_id")
        invite_url = context.user_data.get("campaign_invite_url")

        try:
            completion_limit = int(budget / reward)
        except Exception:
            completion_limit = 0

        if completion_limit <= 0:
            await update.message.reply_text(
                "❌ Reward is too large for this budget. "
                "Increase budget or reduce reward."
            )
            return

        try:
            async with get_session() as session:
                async with session.begin():
                    from services.sponsor_service import SponsorService
                    from models.campaign import Campaign, CampaignStatus, TaskType

                    sponsor = await SponsorService.get_sponsor_by_user(session, user.id)
                    if not sponsor:
                        await update.message.reply_text("❌ No sponsor account found.")
                        return
                    sponsor_id_val = sponsor.id

                    try:
                        task_type = TaskType(task_type_str)
                    except ValueError:
                        task_type = TaskType.CHANNEL_JOIN

                    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=duration)

                    campaign = Campaign(
                        sponsor_id=sponsor_id_val,
                        title=title[:256],
                        description=None,
                        task_type=task_type,
                        telegram_chat_id=chat_id,
                        telegram_username=username,
                        invite_url=invite_url,
                        reward_per_user=reward,
                        completion_limit=completion_limit,
                        completed_count=0,
                        total_budget=budget,
                        reserved_budget=Decimal("0"),
                        spent_budget=Decimal("0"),
                        status=CampaignStatus.PENDING,
                        expires_at=expires_at,
                    )
                    session.add(campaign)
                    await session.flush()
                    campaign_id = campaign.id

            context.user_data.clear()

            display = (
                f"@{username}" if username
                else (str(chat_id) if chat_id else (invite_url or "—"))
            )

            await update.message.reply_text(
                f"✅ <b>Campaign Submitted!</b>\n\n"
                f"📌 ID: <b>#{campaign_id}</b>\n"
                f"📝 Title: {title}\n"
                f"🔗 Channel: {display}\n"
                f"📌 Type: {task_type_str}\n"
                f"💰 Reward/task: <b>{fmt_usdt(reward)} USDT</b>\n"
                f"💵 Total budget: <b>{fmt_usdt(budget)} USDT</b>\n"
                f"👥 Max completions: <b>{completion_limit:,}</b>\n"
                f"⏱ Duration: <b>{duration} day(s)</b>\n\n"
                f"⏳ Your campaign is now <b>pending admin approval</b>.\n"
                f"After approval you'll need to <b>fund it</b> before it goes live.",
                parse_mode="HTML",
                reply_markup=sponsor_main_reply_keyboard(),
            )
            return

        except Exception as e:
            log.exception("Campaign creation failed", error=str(e))
            await update.message.reply_text(
                f"❌ Failed to create campaign:\n<code>{str(e)[:300]}</code>",
                parse_mode="HTML",
                reply_markup=sponsor_main_reply_keyboard(),
            )
            return

    # ── Deposit: enter_tx_hash ──
    if step == "enter_tx_hash":
        if not text.startswith("0x") or len(text) < 60:
            await update.message.reply_text(
                "❌ Invalid transaction hash.\n\n"
                "It should start with <code>0x</code> and be at least 60 characters.",
                parse_mode="HTML",
                reply_markup=sponsor_cancel_reply_keyboard(),
            )
            return
        context.user_data.pop("sponsor_step", None)
        await update.message.reply_text(
            f"✅ Transaction hash received:\n<code>{text}</code>\n\n"
            "Your deposit will be verified shortly. You'll be notified once confirmed.",
            parse_mode="HTML",
            reply_markup=sponsor_main_reply_keyboard(),
        )
        return


# ══════════════════════════════════════════════════════════════════
# Campaign delete flow
# ══════════════════════════════════════════════════════════════════

async def _sponsor_delete_prompt(query, campaign_id: int, sponsor_id: int) -> None:
    """Ask for confirmation before deleting."""
    from keyboards.sponsor_keyboards import campaign_delete_confirm_keyboard

    async with get_session() as session:
        from models.campaign import Campaign

        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            await query.edit_message_text("❌ Campaign not found.")
            return
        if campaign.sponsor_id != sponsor_id:
            await query.edit_message_text("❌ Not your campaign.")
            return

        title = campaign.title
        status_str = _status_str(campaign.status)
        reserved = campaign.reserved_budget or Decimal("0")

    warning = ""
    if status_str in ("ACTIVE", "PAUSED") and reserved > Decimal("0"):
        warning = (
            f"\n⚠️ <b>Warning:</b> This campaign has "
            f"<b>{fmt_usdt(reserved)} USDT</b> reserved budget.\n"
            f"It will be <b>refunded to your balance</b>.\n"
        )

    await query.edit_message_text(
        f"🗑 <b>DELETE CAMPAIGN #{campaign_id}?</b>\n\n"
        f"📝 Title: <b>{title}</b>\n"
        f"📌 Status: <b>{status_str}</b>\n"
        f"{warning}\n"
        f"⚠️ This cannot be undone.\n\n"
        f"Are you sure?",
        parse_mode="HTML",
        reply_markup=campaign_delete_confirm_keyboard(campaign_id),
    )


async def _sponsor_delete_confirm(query, campaign_id: int, sponsor_id: int) -> None:
    """Actually delete the campaign."""
    from services.campaign_service import CampaignService, CampaignValidationError

    try:
        async with get_session() as session:
            async with session.begin():
                summary = await CampaignService.delete_campaign(
                    session=session,
                    campaign_id=campaign_id,
                    actor_id=sponsor_id,
                    actor_is_admin=False,
                )

        released = summary.get("released", Decimal("0"))
        released_line = ""
        if released and released > Decimal("0"):
            released_line = f"\n💰 Refunded: <b>{fmt_usdt(released)} USDT</b>"

        await query.edit_message_text(
            f"✅ <b>Campaign Deleted</b>\n\n"
            f"📌 ID: #{summary['id']}\n"
            f"📝 Title: {summary['title']}"
            f"{released_line}",
            parse_mode="HTML",
        )
    except CampaignValidationError as e:
        await query.edit_message_text(f"❌ {e}")
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise
    except Exception as e:
        log.exception("Delete campaign failed", campaign_id=campaign_id)
        await query.edit_message_text(
            f"❌ Delete failed: <code>{str(e)[:200]}</code>",
            parse_mode="HTML",
        )