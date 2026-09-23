"""
Logging Middleware — structured request logging for every update.
"""
import time
import structlog
from telegram import Update
from telegram.ext import ContextTypes

log = structlog.get_logger(__name__)


class LoggingMiddleware:

    @staticmethod
    async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log incoming updates with user context."""
        user = update.effective_user
        if not user:
            return

        action = "unknown"
        if update.message:
            action = f"message:{(update.message.text or '')[:50]}"
        elif update.callback_query:
            action = f"callback:{update.callback_query.data or ''}"
        elif update.inline_query:
            action = f"inline:{update.inline_query.query[:30]}"

        log.info(
            "Telegram update",
            user_id=user.id,
            username=user.username,
            action=action,
            update_id=update.update_id,
        )
