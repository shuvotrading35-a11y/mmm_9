"""
Start Handler — /start command, user registration, referral parsing.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from keyboards.user_keyboards import main_menu_keyboard
from middlewares.rate_limit_middleware import RateLimitMiddleware
from services.user_service import UserService

log = structlog.get_logger(__name__)

STATES = {}  # No conversation state needed for /start


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start [ref_CODE] — register or welcome back user."""
    user = update.effective_user

    # Rate limit
    if not await RateLimitMiddleware.check_start(user.id):
        await update.message.reply_text("⏳ Too many requests. Please wait a moment.")
        return

    # Parse referral code from deep link: /start ref_ABC123
    referrer_code = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            referrer_code = arg[4:]
        elif arg.startswith("REF"):
            referrer_code = arg

    async with get_session() as session:
        async with session.begin():
            db_user, is_new = await UserService.get_or_create_user(
                session=session,
                tg_user=user,
                referrer_code=referrer_code,
            )
            is_sponsor = db_user.is_sponsor

    from utils.decimal_utils import fmt_usdt

    if is_new:
        text = (
            f"🏛 <b>GLOBAL TASK EARN</b>\n\n"
            f"Welcome, <b>{user.first_name}</b>! 👋\n\n"
            f"💰 Complete Telegram tasks and earn real USDT.\n"
            f"🎁 Invite friends — earn commission on every task they complete.\n"
            f"💳 Withdraw to your BSC wallet instantly.\n\n"
            f"Your balance: <b>0.00000000 USDT</b>\n\n"
            f"⭐ Start earning now!"
        )
    else:
        balance = fmt_usdt(db_user.balance)
        text = (
            f"🏛 <b>GLOBAL TASK EARN</b>\n\n"
            f"Welcome back, <b>{user.first_name}</b>! 👋\n\n"
            f"💰 Balance: <b>{balance} USDT</b>\n\n"
            f"Use the menu below to navigate."
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_sponsor=is_sponsor),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    text = (
        "🆘 <b>HELP — GLOBAL TASK EARN</b>\n\n"
        "<b>How it works:</b>\n"
        "1️⃣ Browse tasks with 📋 View Tasks\n"
        "2️⃣ Complete the task (join a channel/group)\n"
        "3️⃣ Press ✅ DONE to verify and earn USDT\n"
        "4️⃣ Withdraw earnings to your BSC wallet\n\n"
        "<b>Commands:</b>\n"
        "/start — Main menu\n"
        "/profile — Your profile & earnings\n"
        "/tasks — Browse tasks\n"
        "/withdraw — Request withdrawal\n"
        "/referral — Your referral link\n"
        "/stats — Platform statistics\n\n"
        "<b>Support:</b>\n"
        "Use 🆘 Support in the menu to create a ticket."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def _is_user_sponsor(user_id: int) -> bool:
    """Check if user has an APPROVED sponsor account."""
    try:
        async with get_session() as session:
            from services.sponsor_service import SponsorService
            sponsor = await SponsorService.get_sponsor_by_user(session, user_id)
            if sponsor is not None:
                status_str = (
                    sponsor.status.value if hasattr(sponsor.status, "value")
                    else str(sponsor.status)
                )
                return status_str == "APPROVED"
    except Exception:
        log.exception("Failed to check sponsor status via SponsorService")

    # Fallback: user flag
    try:
        async with get_session() as session:
            db_user = await UserService.get_user(session, user_id)
            return bool(db_user and db_user.is_sponsor)
    except Exception:
        log.exception("Failed to check sponsor flag on user")
        return False


async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """🏠 Main Menu button — re-show the main menu."""
    user = update.effective_user
    is_sponsor = await _is_user_sponsor(user.id)

    await update.message.reply_text(
        "🏠 <b>Main Menu</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_sponsor=is_sponsor),
    )


async def handle_user_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """❌ Cancel button — clear user_data and return to main menu."""
    context.user_data.clear()
    user = update.effective_user
    is_sponsor = await _is_user_sponsor(user.id)

    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=main_menu_keyboard(is_sponsor=is_sponsor),
    )