"""
Profile Handler — view profile and set BSC wallet.
"""
import structlog
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CommandHandler, filters
)

from database import get_session
from keyboards.user_keyboards import cancel_keyboard, main_menu_keyboard
from utils.decimal_utils import fmt_usdt
from utils.time_utils import fmt_date
from utils.wallet_utils import validate_bsc_address, mask_wallet

log = structlog.get_logger(__name__)

WALLET_INPUT = 1


async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user profile."""
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

    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💳 Set/Update BSC Wallet",
            callback_data="profile_set_wallet"
        )]
    ])

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def wallet_set_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to enter BSC wallet."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "💳 <b>Set BSC Wallet</b>\n\n"
        "Please send your BNB Smart Chain (BSC) wallet address.\n"
        "⚠️ Make sure it's a valid BEP-20 wallet you control.\n\n"
        "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("profile_cancel"),
    )
    return WALLET_INPUT


async def handle_set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and validate BSC wallet address."""
    user = update.effective_user
    address = update.message.text.strip()

    if not validate_bsc_address(address):
        await update.message.reply_text(
            "❌ Invalid BSC wallet address.\n"
            "Please send a valid EIP-55 checksummed address.\n\n"
            "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("profile_cancel"),
        )
        return WALLET_INPUT

    async with get_session() as session:
        async with session.begin():
            from services.user_service import UserService
            await UserService.set_bsc_wallet(session, user.id, address)

    # Fraud check: duplicate wallet
    async with get_session() as session:
        from services.fraud_service import FraudService
        async with session.begin():
            await FraudService.check_duplicate_wallet(session, user.id, address)

    await update.message.reply_text(
        f"✅ BSC wallet updated!\n\n"
        f"<code>{mask_wallet(address)}</code>\n\n"
        f"You can now request withdrawals.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def wallet_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("❌ Wallet update cancelled.")
    return ConversationHandler.END


def profile_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^👤 Profile$"), handle_profile),
            CommandHandler("profile", handle_profile),
        ],
        states={
            WALLET_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_wallet),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^/cancel$"), wallet_cancel),
        ],
        per_message=False,
    )
