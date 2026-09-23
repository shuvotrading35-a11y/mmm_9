"""
Force Join Middleware — mandatory channel membership gate.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from config import settings

log = structlog.get_logger(__name__)


class ForceJoinMiddleware:

    @staticmethod
    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Returns True if user passes force-join check (or feature is disabled).
        Returns False if user must join channels first.
        """
        if not settings.FORCE_JOIN_ENABLED:
            return True

        user = update.effective_user
        if not user:
            return True

        # Admins bypass force join
        if settings.is_admin(user.id):
            return True

        # Allow force_join_check callback to pass through
        if update.callback_query and update.callback_query.data == "force_join_check":
            return True

        from database import get_session
        from services.force_join_service import ForceJoinService

        async with get_session() as session:
            all_joined, missing = await ForceJoinService.check_user_membership(
                bot=context.bot,
                session=session,
                user_id=user.id,
            )

        if all_joined:
            return True

        # User must join before continuing
        keyboard = ForceJoinService.build_join_keyboard(missing)
        msg = (
            "📢 <b>Join Required</b>\n\n"
            "To use this bot, please join our official channel(s) first:\n\n"
            "After joining, tap the button below to continue. ✅"
        )

        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=keyboard)
        elif update.callback_query:
            await update.callback_query.answer(
                "Please join our channel first!", show_alert=True
            )
            await update.callback_query.message.reply_text(
                msg, parse_mode="HTML", reply_markup=keyboard
            )

        return False
