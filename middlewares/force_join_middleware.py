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
    _last_prompt: dict = {}

    # How long to suppress duplicate full prompts (seconds)
    _COOLDOWN = 1

    @staticmethod
    async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Returns True if user passes force-join check (or feature is disabled).
        Returns False if user must join channels first.
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
            # Clear cooldown so a future leave triggers prompt instantly
            ForceJoinMiddleware._last_prompt.pop(user.id, None)
            return True

        # ── Rate limit: don't spam the same user ──
        now = time.time()
        last = ForceJoinMiddleware._last_prompt.get(user.id, 0)
        if now - last < ForceJoinMiddleware._COOLDOWN:
            # Already prompted recently — give quick feedback so the
            # button doesn't feel "stuck".
            try:
                if update.callback_query:
                    await update.callback_query.answer(
                        "⚠️ Please join our channel first!",
                        show_alert=False,
                    )
            except Exception:
                pass
            return False

        ForceJoinMiddleware._last_prompt[user.id] = now

        # Build full prompt
        total = len(missing)
        keyboard = ForceJoinService.build_join_keyboard(missing)

        display_name = user.first_name or "Friend"

        msg = (
            f"❌ <b>Must Join All Channels To Use The Bot & Unlock Tasks!</b>\n\n"
            f"👋 Hey <b>{display_name}</b>,\n\n"
            f"📌 You need to join <b>{total}</b> channel(s) below.\n"
            f"👉 Tap each button, join the channel, then come back and "
            f"tap <b>✅ Joined - Check</b>."
        )

        try:
            if update.message:
                await update.message.reply_text(
                    msg, parse_mode="HTML", reply_markup=keyboard
                )
            elif update.callback_query:
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