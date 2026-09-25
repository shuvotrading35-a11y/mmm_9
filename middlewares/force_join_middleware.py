"""
Force Join Middleware — mandatory channel membership gate.
"""
import time

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from config import settings

log = structlog.get_logger(__name__)


class ForceJoinMiddleware:

    # In-memory rate limit: user_id → last prompt time (unix seconds)
    # Prevents spamming the same user across rapid button presses.
    _last_prompt: dict = {}

    # How long to suppress duplicate prompts (seconds)
    _COOLDOWN = 3

    @staticmethod
    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Returns True if user passes force-join check (or feature is disabled).
        Returns False if user must join channels first (prompt sent).
        """
        # Feature toggle
        if not settings.FORCE_JOIN_ENABLED:
            return True

        user = update.effective_user
        if not user:
            return True

        # Admins bypass
        if settings.is_admin(user.id):
            return True

        # Allow the verify button to always pass through
        if update.callback_query and update.callback_query.data == "force_join_check":
            return True

        # Look up membership
        from database import get_session
        from services.force_join_service import ForceJoinService

        async with get_session() as session:
            all_joined, missing = await ForceJoinService.check_user_membership(
                bot=context.bot,
                session=session,
                user_id=user.id,
            )

        if all_joined:
            # Clear any stale cooldown so a future leave triggers prompt instantly
            ForceJoinMiddleware._last_prompt.pop(user.id, None)
            return True

        # ── Rate limit: don't spam the same user ──
        now = time.time()
        last = ForceJoinMiddleware._last_prompt.get(user.id, 0)
        if now - last < ForceJoinMiddleware._COOLDOWN:
            # Already prompted recently — silently block
            return False

        ForceJoinMiddleware._last_prompt[user.id] = now

        # Build prompt
        keyboard = ForceJoinService.build_join_keyboard(missing)
        msg = (
            "📢 <b>Join Required</b>\n\n"
            "To use this bot, please join our official channel(s) first:\n\n"
            "After joining, tap the button below to continue. ✅"
        )

        try:
            if update.message:
                await update.message.reply_text(
                    msg, parse_mode="HTML", reply_markup=keyboard
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    "Please join our channel first!", show_alert=True
                )
                # Edit the original message if possible, otherwise send new
                try:
                    await update.callback_query.edit_message_text(
                        msg, parse_mode="HTML", reply_markup=keyboard
                    )
                except Exception:
                    await update.callback_query.message.reply_text(
                        msg, parse_mode="HTML", reply_markup=keyboard
                    )
        except Exception:
            log.exception("Failed to send force-join prompt", user_id=user.id)

        return False