"""
Withdraw Handler — multi-step withdrawal conversation.
Steps: wallet → amount → confirm → submit
"""
import structlog
from decimal import Decimal
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)

from config import settings
from database import get_session
from keyboards.user_keyboards import withdraw_confirm_keyboard, cancel_keyboard
from middlewares.rate_limit_middleware import RateLimitMiddleware
from services.withdrawal_service import WithdrawalService, WithdrawalValidationError
from services.notification_service import NotificationService
from utils.decimal_utils import fmt_usdt, parse_usdt
from utils.wallet_utils import validate_bsc_address, mask_wallet

log = structlog.get_logger(__name__)

ENTER_WALLET, ENTER_AMOUNT, CONFIRM = range(3)


async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point — show balance and request wallet."""
    user = update.effective_user
    message = update.message

    # Rate limit
    if not await RateLimitMiddleware.check_withdrawal(user.id):
        await message.reply_text("⏳ Too many withdrawal attempts. Please wait before trying again.")
        return ConversationHandler.END

    # Load user balance
    async with get_session() as session:
        from models.user import User
        db_user = await session.get(User, user.id)
        if not db_user:
            await message.reply_text("Please use /start first.")
            return ConversationHandler.END
        balance = db_user.balance
        saved_wallet = db_user.bsc_wallet

    text = (
        f"💳 <b>WITHDRAWAL</b>\n\n"
        f"💰 Available Balance: <b>{fmt_usdt(balance)} USDT</b>\n"
        f"📉 Minimum: <b>{settings.MIN_WITHDRAWAL} USDT</b>\n"
        f"📈 Maximum: <b>{settings.MAX_WITHDRAWAL} USDT</b>\n"
        f"🌐 Network: BNB Smart Chain (BSC)\n\n"
    )

    if saved_wallet:
        text += f"💳 Saved wallet: <code>{mask_wallet(saved_wallet)}</code>\n\n"
        text += "Send your BSC wallet address, or press Skip to use your saved wallet:"
        context.user_data["saved_wallet"] = saved_wallet
    else:
        text += "Please send your BSC wallet address (BEP-20):"

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=cancel_keyboard("withdraw_cancel"),
    )
    return ENTER_WALLET


async def withdraw_enter_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive BSC wallet address."""
    text = update.message.text.strip()

    # Allow "skip" to use saved wallet
    if text.lower() in ("skip", "/skip") and context.user_data.get("saved_wallet"):
        wallet = context.user_data["saved_wallet"]
    else:
        wallet = text
        if not validate_bsc_address(wallet):
            await update.message.reply_text(
                "❌ Invalid BSC wallet address. Please send a valid checksummed address.\n\n"
                "Example: <code>0x742d35Cc6634C0532925a3b844Bc454e4438f44e</code>",
                parse_mode="HTML",
                reply_markup=cancel_keyboard("withdraw_cancel"),
            )
            return ENTER_WALLET

    context.user_data["withdraw_wallet"] = wallet
    await update.message.reply_text(
        f"✅ Wallet: <code>{mask_wallet(wallet)}</code>\n\n"
        f"💵 Now enter the amount to withdraw (USDT):\n"
        f"Min: {settings.MIN_WITHDRAWAL} | Max: {settings.MAX_WITHDRAWAL}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard("withdraw_cancel"),
    )
    return ENTER_AMOUNT


async def withdraw_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive withdrawal amount."""
    user = update.effective_user
    raw_amount = update.message.text.strip()

    try:
        amount = parse_usdt(raw_amount)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a valid number (e.g. 0.5)",
            reply_markup=cancel_keyboard("withdraw_cancel"),
        )
        return ENTER_AMOUNT

    wallet = context.user_data.get("withdraw_wallet")

    # Pre-validate (shows errors before confirmation screen)
    async with get_session() as session:
        try:
            await WithdrawalService.validate_withdrawal_request(
                session=session,
                user_id=user.id,
                amount=amount,
                destination_wallet=wallet,
            )
        except WithdrawalValidationError as e:
            await update.message.reply_text(str(e), parse_mode="HTML")
            return ENTER_AMOUNT

    context.user_data["withdraw_amount"] = str(amount)

    await update.message.reply_text(
        f"💸 <b>WITHDRAWAL CONFIRMATION</b>\n\n"
        f"Amount:   <b>{fmt_usdt(amount)} USDT</b>\n"
        f"Network:  BNB Smart Chain (BSC)\n"
        f"To:       <code>{mask_wallet(wallet)}</code>\n\n"
        f"⚠️ This action is irreversible.",
        parse_mode="HTML",
        reply_markup=withdraw_confirm_keyboard(),
    )
    return CONFIRM


async def withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User confirmed — create withdrawal."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    amount = Decimal(context.user_data["withdraw_amount"])
    wallet = context.user_data["withdraw_wallet"]

    async with get_session() as session:
        async with session.begin():
            try:
                withdrawal = await WithdrawalService.create_withdrawal(
                    session=session,
                    user_id=user.id,
                    amount=amount,
                    destination_wallet=wallet,
                )
            except WithdrawalValidationError as e:
                await query.edit_message_text(str(e), parse_mode="HTML")
                return ConversationHandler.END
            except Exception as e:
                log.error("Withdrawal creation failed", error=str(e))
                await query.edit_message_text("❌ Failed to create withdrawal. Please try again.")
                return ConversationHandler.END

    import asyncio
    asyncio.create_task(NotificationService.withdrawal_created(user.id, amount))

    # Notify admin for large withdrawals
    if amount >= Decimal("50"):
        asyncio.create_task(
            NotificationService.notify_admin_large_withdrawal(user.id, amount, withdrawal.id)
        )

    await query.edit_message_text(
        f"✅ <b>Withdrawal Submitted!</b>\n\n"
        f"💵 Amount: <b>{fmt_usdt(amount)} USDT</b>\n"
        f"📋 Reference: #WD{withdrawal.id:06d}\n"
        f"⏳ Status: <b>Pending Processing</b>\n\n"
        f"You'll be notified once it's processed.",
        parse_mode="HTML",
    )
    context.user_data.clear()
    return ConversationHandler.END


async def withdraw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel withdrawal."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Withdrawal cancelled.")
    else:
        await update.message.reply_text("❌ Withdrawal cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def withdraw_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^💳 Withdraw$"), withdraw_start),
            CommandHandler("withdraw", withdraw_start),
        ],
        states={
            ENTER_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_enter_wallet),
            ],
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_enter_amount),
            ],
            CONFIRM: [
                CallbackQueryHandler(withdraw_confirm, pattern="^withdraw_confirm$"),
                CallbackQueryHandler(withdraw_cancel, pattern="^withdraw_cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(withdraw_cancel, pattern="^withdraw_cancel$"),
            CommandHandler("cancel", withdraw_cancel),
        ],
        per_message=False,
    )
