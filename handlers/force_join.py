"""
Force Join Handler — handles the 'I've Joined' callback.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from services.force_join_service import ForceJoinService

log = structlog.get_logger(__name__)


async def handle_force_join_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User claims to have joined all required channels — re-check."""
    query = update.callback_query
    user = update.effective_user
    await query.answer("⏳ Checking...")

    async with get_session() as session:
        all_joined, missing = await ForceJoinService.check_user_membership(
            bot=context.bot,
            session=session,
            user_id=user.id,
        )

    if all_joined:
        # Delete the join-prompt message (optional)
        try:
            await query.message.delete()
        except Exception:
            pass

        # Determine sponsor status
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

        # Send main menu directly — do NOT call cmd_start
        # (cmd_start needs update.message; it's None in a callback context)
        from keyboards.user_keyboards import main_menu_keyboard

        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"✅ <b>Verified!</b>\n\n"
                f"Welcome, <b>{user.first_name}</b>! 👋\n\n"
                f"Use the menu below to start earning."
            ),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_sponsor=is_sponsor),
        )
    else:
        keyboard = ForceJoinService.build_join_keyboard(missing)
        try:
            await query.edit_message_text(
                "❌ You haven't joined all required channels yet.\n\n"
                "Please join and try again:",
                reply_markup=keyboard,
            )
        except Exception:
            # Fallback if edit fails (e.g. message deleted)
            await context.bot.send_message(
                chat_id=user.id,
                text="❌ Please join all required channels first:",
                reply_markup=keyboard,
            )