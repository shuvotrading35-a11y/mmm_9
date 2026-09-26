"""
Profile Handler — view profile and set BSC wallet.
Uses single-message menu pattern (auto-delete previous).
"""
import structlog
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters,
)

from database import get_session
from keyboards.user_keyboards import cancel_keyboard, main_menu_keyboard
from utils.decimal_utils import fmt_usdt
from utils.time_utils import fmt_date
from utils.wallet_utils import validate_bsc_address, mask_wallet
from utils.menu import send_menu

log = structlog.get_logger(__name__)

WALLET_INPUT = 1


# ══════════════════════════════════════════════════════════════════
# Profile view
# ══════════════════════════════════════════════════════════════════

async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user profile (menu-style — deletes previous menu message)."""
    user = update.effective_user

    async with get_session() as session:
        from models.user import User
        from services.user_service import UserService

        db_user = await session.get(User, user.id)
        if not db_user:
            await send_menu(
                update, context,
                text="Please use /start first.",
            )
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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💳 Set/Update BSC Wallet",
            callback_data="profile_set_wallet",
        )]
    ])

    await send_menu(
        update, context,
        text=text,
        reply_markup=keyboard,
    )


# ══════════════════════════════════════════════════════════════════
# Wallet set flow (ConversationHandler)
# ══════════════════════════════════════════════════════════════════

async def wallet_set_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to enter BSC wallet — edits the existing profile message in place."""
    query = update.callback_query
    await query.answer()

    prompt_text = (
        "💳 <b>Set BSC Wallet</b>\n\n"
        "Please send your BNB Smart Chain (BSC) wallet address.\n"
        "⚠️ Make sure it's a valid BEP-20 wallet you control.\n\n"
        "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>"
    )

    # Try to edit the profile message in place — cleanest UX
    try:
        await query.edit_message_text(
            prompt_text,
            parse_mode="HTML",
            reply_markup=cancel_keyboard("profile_cancel"),
        )
        return WALLET_INPUT
    except Exception:
        pass

    # Fallback — delete previous menu, send a fresh prompt
    chat_id = update.effective_chat.id
    key = f"menu_msg_id_{chat_id}"
    prev_id = context.user_data.get(key)
    if prev_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception:
            pass

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=prompt_text,
        parse_mode="HTML",
        reply_markup=cancel_keyboard("profile_cancel"),
    )
    context.user_data[key] = sent.message_id
    return WALLET_INPUT


async def handle_set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and validate BSC wallet address."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    address = (update.message.text or "").strip()

    # Delete the user's wallet input message (keep chat clean)
    try:
        await update.message.delete()
    except Exception:
        pass

    # ── Validation ──
    if not validate_bsc_address(address):
        error_text = (
            "❌ Invalid BSC wallet address.\n"
            "Please send a valid EIP-55 checksummed address.\n\n"
            "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>"
        )
        try:
            # Edit the prompt message to show the error
            await update.effective_chat.send_message(
                chat_id=chat_id,
                text=error_text,
                parse_mode="HTML",
                reply_markup=cancel_keyboard("profile_cancel"),
            )
        except Exception:
            pass
        return WALLET_INPUT

    # ── Save ──
    async with get_session() as session:
        async with session.begin():
            from services.user_service import UserService
            await UserService.set_bsc_wallet(session, user.id, address)

    # ── Fraud check ──
    try:
        async with get_session() as session:
            from services.fraud_service import FraudService
            async with session.begin():
                await FraudService.check_duplicate_wallet(session, user.id, address)
    except Exception:
        log.exception("Fraud check failed", user_id=user.id)

    # ── Delete prompt, show success + main menu ──
    key = f"menu_msg_id_{chat_id}"
    prev_id = context.user_data.get(key)
    if prev_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception:
            pass

    await send_menu(
        update, context,
        text=(
            f"✅ <b>BSC Wallet Updated!</b>\n\n"
            f"<code>{mask_wallet(address)}</code>\n\n"
            f"You can now request withdrawals."
        ),
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def wallet_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel wallet update — clean up and return to main menu."""
    if update.callback_query:
        await update.callback_query.answer()
        chat_id = update.effective_chat.id
        key = f"menu_msg_id_{chat_id}"
        prev_id = context.user_data.get(key)
        if prev_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
            except Exception:
                pass

        sent = await context.bot.send_message(
            chat_id=chat_id,
            text="❌ <b>Wallet update cancelled.</b>",
            parse_mode="HTML",
        )
        context.user_data[key] = sent.message_id
        return ConversationHandler.END

    # Fallback via /cancel command
    try:
        await update.message.delete()
    except Exception:
        pass
    await send_menu(
        update, context,
        text="❌ <b>Wallet update cancelled.</b>",
    )
    return ConversationHandler.END


def profile_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            # Triggered by inline button in the profile message
            CallbackQueryHandler(wallet_set_prompt, pattern=r"^profile_set_wallet$"),
        ],
        states={
            WALLET_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_wallet),
                CallbackQueryHandler(wallet_cancel, pattern=r"^profile_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", wallet_cancel),
        ],
        per_message=False,
    )