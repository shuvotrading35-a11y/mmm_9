"""
Maintenance Middleware — blocks all non-admin users when maintenance mode is ON.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from config import settings

log = structlog.get_logger(__name__)


class MaintenanceMiddleware:

    @staticmethod
    async def process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Block non-admins during maintenance."""
        if not settings.MAINTENANCE_MODE:
            return  # Pass through

        user = update.effective_user
        if not user:
            return

        if settings.is_admin(user.id):
            return  # Admins bypass maintenance

        if update.message:
            await update.message.reply_text(
                "🔧 <b>System Maintenance</b>\n\n"
                "Global Task Earn is temporarily under maintenance.\n"
                "Please try again later. We'll be back soon! 🚀",
                parse_mode="HTML",
            )
        elif update.callback_query:
            await update.callback_query.answer(
                "System under maintenance. Please try again later.",
                show_alert=True,
            )

    @staticmethod
    async def process_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await MaintenanceMiddleware.process(update, context)
