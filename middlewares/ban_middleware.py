"""
Ban Middleware — early exit for banned users.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

log = structlog.get_logger(__name__)


class BanMiddleware:

    @staticmethod
    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Returns True if user is banned (should stop processing)."""
        user = update.effective_user
        if not user:
            return False

        from database import get_session
        from models.user import User, UserStatus

        async with get_session() as session:
            db_user = await session.get(User, user.id)
            if db_user and db_user.status == UserStatus.BANNED:
                if update.message:
                    await update.message.reply_text(
                        "🚫 Your account has been banned.\n"
                        "Contact support if you believe this is an error."
                    )
                elif update.callback_query:
                    await update.callback_query.answer(
                        "Your account is banned.", show_alert=True
                    )
                return True
        return False
