"""
Profile Handler — view profile and set BSC wallet.
Flag-based state — menu buttons never get stuck.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from keyboards.user_keyboards import (
    profile_keyboard,
    main_menu_keyboard,
    cancel_keyboard,
)
from utils.decimal_utils import fmt_usdt
from utils.time_utils import fmt_date
from utils.wallet_utils import validate_bsc_address, mask_wallet

log = structlog.get_logger(__name__)

WALLET_FLAG = "awaiting_wallet"

MENU_BUTTONS = {
    "👤 Profile", "💰 Live Payments", "📋 View Tasks", "🎁 Referral",
    "💳 Withdraw", "📊 Stats", "📣 Promotion", "🆘 Support",
    "💼 Sponsor Panel", "🏠 Main Menu", "🔙 Back to Main Menu",
    "💳 Set/Update Wallet", "❌ Cancel",
}


async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user profile."""
    context.user_data.pop(WALLET_FLAG, None)

    user = update.effective_user

    async with get_session() as session:
        from models.user import User
        from services.user_service import UserService

        db_user = await session.get(User, user.id)
        if not db_user:
            await update.message.reply_text("Please use /start first.")
            return

        ref_stats = await UserService.get_referral_stats(session, user.id)

    wallet_display = (
        mask_wallet(db_user.bsc_wallet)
        if db_user.bsc_wallet
        else "Not set — tap below to add"
    )

    text = (
        f"👤 <b>YOUR PROFILE</b>\n\n"
        f"🆔 ID: <code>{db_user.id}</code>\n"
        f"👤 Username: {('@' + db_user.username) if db_user.username else 'N/A'}\n\n"
        f"━━━━━━ EARNINGS ━━━━━━\n"
        f"💰 Balance:          <b>{fmt_usdt(db_user.balance)} USDT</b>\n"
        f"💎 Total Earned:     <b>{fmt_usdt(db_user.total_earned)} USDT</b>\n"
        f"💳 Total Withdrawn:  <b>{fmt_usdt(db_user.total_withdrawn)} USDT</b>\n\n"
        f"━━━━━━ ACTIVITY ━━━━━━\n"
        f"📋 Tasks Completed:  <b>{db_user.tasks_completed}</b>\n"
        f"⏭  Tasks Skipped:    <b>{db_user.tasks_skipped}</b>\n\n"
        f"━━━━━━ REFERRALS ━━━━━━\n"
        f"👥 Referrals:        <b>{ref_stats['total_referrals']}</b>\n"
        f"🎁 Referral Earned:  <b>{fmt_usdt(ref_stats['signup_rewards'])} USDT</b>\n"
        f"💸 Commission:       <b>{fmt_usdt(ref_stats['commission_earned'])} USDT</b>\n\n"
        f"━━━━━━ WALLET ━━━━━━\n"
        f"💳 BSC Wallet: <code>{wallet_display}</code>\n"
        f"📅 Joined: {fmt_date(db_user.joined_at)}"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=profile_keyboard(),
    )


async def wallet_set_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed '💳 Set/Update Wallet' — set flag and ask for address."""
    context.user_data[WALLET_FLAG] = True

    await update.message.reply_text(
        "💳 <b>Set BSC Wallet</b>\n\n"
        "Please send your BNB Smart Chain (BSC) wallet address.\n"
        "⚠️ Make sure it's a valid BEP-20 wallet you control.\n\n"
        "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>\n\n"
        "Or tap 👤 Profile / 🏠 Main Menu to cancel.",
        parse_mode="HTML",
        reply_markup=profile_keyboard(),
    )


async def handle_set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive and validate BSC wallet address (only called by router)."""
    user = update.effective_user
    address = (update.message.text or "").strip()

    if not validate_bsc_address(address):
        await update.message.reply_text(
            "❌ <b>Invalid BSC wallet address.</b>\n\n"
            "Please send a valid EVM address (0x + 40 hex characters).\n\n"
            "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
            parse_mode="HTML",
            reply_markup=profile_keyboard(),
        )
        return

    async with get_session() as session:
        async with session.begin():
            from services.user_service import UserService
            await UserService.set_bsc_wallet(session, user.id, address)

    try:
        async with get_session() as session:
            from services.fraud_service import FraudService
            async with session.begin():
                await FraudService.check_duplicate_wallet(session, user.id, address)
    except Exception:
        log.exception("Fraud check failed", user_id=user.id)

    context.user_data.pop(WALLET_FLAG, None)

    await update.message.reply_text(
        f"✅ <b>BSC Wallet Updated!</b>\n\n"
        f"<code>{mask_wallet(address)}</code>\n\n"
        f"You can now request withdrawals.",
        parse_mode="HTML",
        reply_markup=profile_keyboard(),
    )


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Back to main menu from profile screen."""
    context.user_data.pop(WALLET_FLAG, None)

    user = update.effective_user

    is_sponsor = False
    try:
        async with get_session() as session:
            from services.sponsor_service import SponsorService
            sponsor = await SponsorService.get_sponsor_by_user(session, user.id)
            if sponsor is not None:
                status_str = (
                    sponsor.status.value if hasattr(sponsor.status, "value")
                    else str(sponsor.status)
                )
                is_sponsor = (status_str == "APPROVED")
    except Exception:
        log.exception("Failed to check sponsor status")

    await update.message.reply_text(
        "🏠 <b>Main Menu</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_sponsor=is_sponsor),
    )


async def wallet_input_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Catch-all router: only handles wallet input when the flag is set.
    Menu buttons clear the flag and let their own handlers process them.
    """
    if not context.user_data.get(WALLET_FLAG):
        return

    text = (update.message.text or "").strip()

    # If user tapped any menu button, cancel the wallet flow
    if text in MENU_BUTTONS:
        context.user_data.pop(WALLET_FLAG, None)
        return  # let the specific handler (registered earlier) run

    # Otherwise, treat the text as a wallet address
    await handle_set_wallet(update, context)