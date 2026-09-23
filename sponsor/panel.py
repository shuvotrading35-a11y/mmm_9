"""
Sponsor Panel — campaign management and wallet for approved sponsors.
"""
import structlog
from decimal import Decimal
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from keyboards.sponsor_keyboards import (
    sponsor_main_keyboard, task_type_keyboard,
    duration_keyboard, campaign_actions_keyboard,
    deposit_submitted_keyboard,
)
from utils.decimal_utils import fmt_usdt

log = structlog.get_logger(__name__)


async def _get_sponsor(session, user_id: int):
    from services.sponsor_service import SponsorService
    return await SponsorService.get_sponsor_by_user(session, user_id)


async def sponsor_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry — show sponsor panel or apply prompt."""
    user = update.effective_user
    message = update.message

    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)

        if not sponsor:
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            await message.reply_text(
                "💼 <b>SPONSOR PANEL</b>\n\n"
                "You don't have a sponsor account yet.\n"
                "Apply to become a sponsor and run advertising campaigns.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 Apply as Sponsor", callback_data="sponsor:apply")],
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

        from models.campaign import Campaign, CampaignStatus
        from sqlalchemy import select, func as sa_func

        active = (await session.execute(
            select(sa_func.count(Campaign.id)).where(
                Campaign.sponsor_id == sponsor.id,
                Campaign.status == CampaignStatus.ACTIVE
            )
        )).scalar()
        paused = (await session.execute(
            select(sa_func.count(Campaign.id)).where(
                Campaign.sponsor_id == sponsor.id,
                Campaign.status == CampaignStatus.PAUSED
            )
        )).scalar()
        completed = (await session.execute(
            select(sa_func.count(Campaign.id)).where(
                Campaign.sponsor_id == sponsor.id,
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

    await message.reply_text(text, parse_mode="HTML", reply_markup=sponsor_main_keyboard())


async def sponsor_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all sponsor: callbacks."""
    query = update.callback_query
    user = update.effective_user
    await query.answer()

    data = query.data
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    # Verify sponsor
    async with get_session() as session:
        sponsor = await _get_sponsor(session, user.id)

    if action == "apply":
        await _sponsor_apply(query, user.id)
        return

    if not sponsor:
        await query.edit_message_text("❌ No sponsor account found.")
        return

    if action == "create_campaign":
        context.user_data.clear()
        await query.edit_message_text(
            "📋 <b>CREATE CAMPAIGN</b>\n\nSelect task type:",
            parse_mode="HTML",
            reply_markup=task_type_keyboard(),
        )
    elif action == "type" and len(parts) > 2:
        context.user_data["campaign_type"] = parts[2]
        await query.edit_message_text(
            f"✅ Type: {parts[2]}\n\n"
            "Please send the Telegram channel/group @username or Chat ID:",
        )
        context.user_data["sponsor_step"] = "enter_username"

    elif action == "campaigns":
        await _sponsor_list_campaigns(query, sponsor.id)

    elif action == "fund" and len(parts) > 2:
        await _sponsor_fund_campaign(query, int(parts[2]), sponsor.id)

    elif action == "deposit":
        await _sponsor_deposit_info(query)
        context.user_data["sponsor_step"] = "enter_tx_hash"

    elif action == "wallet":
        await _sponsor_wallet_info(query, sponsor.id)

    elif action == "analytics" and len(parts) > 2:
        await _sponsor_campaign_analytics(query, int(parts[2]))

    elif action == "back":
        await query.edit_message_text(
            "💼 <b>SPONSOR PANEL</b>",
            parse_mode="HTML",
            reply_markup=sponsor_main_keyboard(),
        )

    elif action == "cancel":
        context.user_data.clear()
        await query.edit_message_text(
            "❌ Cancelled.",
            reply_markup=sponsor_main_keyboard(),
        )


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

    if not campaigns:
        await query.edit_message_text(
            "📋 No campaigns yet. Create your first one!",
            reply_markup=sponsor_main_keyboard(),
        )
        return

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for c in campaigns[:10]:
        status_icon = {"ACTIVE": "🟢", "PAUSED": "⏸", "COMPLETED": "✅",
                       "PENDING": "⏳", "EXPIRED": "❌"}.get(c.status, "•")
        buttons.append([InlineKeyboardButton(
            f"{status_icon} #{c.id}: {c.title[:25]}",
            callback_data=f"sponsor:campaign_detail:{c.id}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="sponsor:back")])

    await query.edit_message_text(
        "📋 <b>MY CAMPAIGNS</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _sponsor_fund_campaign(query, campaign_id: int, sponsor_id: int) -> None:
    async with get_session() as session:
        async with session.begin():
            from services.campaign_service import CampaignService, CampaignValidationError
            try:
                campaign = await CampaignService.fund_campaign(session, campaign_id, sponsor_id)
                await query.edit_message_text(
                    f"✅ Campaign <b>#{campaign_id}</b> funded and now ACTIVE!\n"
                    f"Budget: <b>{fmt_usdt(campaign.total_budget)} USDT</b>",
                    parse_mode="HTML",
                )
            except CampaignValidationError as e:
                await query.edit_message_text(f"❌ {e}")


async def _sponsor_deposit_info(query) -> None:
    from config import settings
    await query.edit_message_text(
        f"💰 <b>DEPOSIT USDT</b>\n\n"
        f"Send USDT (BEP-20) to:\n"
        f"<code>{settings.PAYOUT_WALLET_ADDRESS}</code>\n\n"
        f"🌐 Network: BNB Smart Chain (BSC)\n"
        f"📜 Contract: <code>{settings.USDT_CONTRACT_ADDRESS}</code>\n"
        f"💵 Minimum: {settings.SPONSOR_MIN_DEPOSIT} USDT\n"
        f"⏳ Confirmations: {settings.MIN_DEPOSIT_CONFIRMATIONS} blocks\n\n"
        f"After sending, reply with your <b>Transaction Hash</b> (0x...):",
        parse_mode="HTML",
    )


async def _sponsor_wallet_info(query, sponsor_id: int) -> None:
    from services.sponsor_service import SponsorService
    async with get_session() as session:
        info = await SponsorService.get_sponsor_wallet_info(session, sponsor_id)

    await query.edit_message_text(
        f"💼 <b>WALLET INFO</b>\n\n"
        f"💰 Available: <b>{fmt_usdt(info['available_balance'])} USDT</b>\n"
        f"🔒 Reserved: <b>{fmt_usdt(info['reserved_balance'])} USDT</b>\n"
        f"📊 Total Deposited: <b>{fmt_usdt(info['total_deposited'])} USDT</b>\n"
        f"💸 Total Spent: <b>{fmt_usdt(info['total_spent'])} USDT</b>\n\n"
        f"Deposit Address:\n<code>{info['deposit_address']}</code>\n"
        f"Network: {info['network']}\n"
        f"Minimum: {info['minimum_deposit']} USDT",
        parse_mode="HTML",
        reply_markup=sponsor_main_keyboard(),
    )


async def _sponsor_campaign_analytics(query, campaign_id: int) -> None:
    async with get_session() as session:
        from services.campaign_service import CampaignService
        data = await CampaignService.get_campaign_analytics(session, campaign_id)

    if not data:
        await query.edit_message_text("❌ Campaign not found.")
        return

    await query.edit_message_text(
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
        f"💰 Remaining: <b>{fmt_usdt(data['remaining_budget'])} USDT</b>",
        parse_mode="HTML",
        reply_markup=campaign_actions_keyboard(campaign_id, data['status']),
    )
