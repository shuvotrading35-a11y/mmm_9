"""
Force Join Handler — handles the 'I've Joined' callback.
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import get_session
from services.force_join_service import ForceJoinService


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
        from handlers.start import cmd_start
        await query.edit_message_text("✅ Verified! You can now use the bot.")
        await cmd_start(update, context)
    else:
        keyboard = ForceJoinService.build_join_keyboard(missing)
        await query.edit_message_text(
            "❌ You haven't joined all required channels yet.\n\n"
            "Please join and try again:",
            reply_markup=keyboard,
        )
