"""
Support Handler — ticket creation conversation.
Menu buttons escape the conversation cleanly.
"""
import random
import string
import asyncio
from typing import Optional

import structlog
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram._utils.types import JSONDict
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CommandHandler, CallbackQueryHandler, filters
)

from config import settings
from database import get_session
from middlewares.rate_limit_middleware import RateLimitMiddleware

log = structlog.get_logger(__name__)

SELECT_CATEGORY, ENTER_SUBJECT, ENTER_MESSAGE = range(3)

CATEGORIES = {
    "PAYMENT":    "💳 Payment",
    "TASK":       "📋 Task Issue",
    "WITHDRAWAL": "💵 Withdrawal",
    "REFERRAL":   "🎁 Referral",
    "OTHER":      "❓ Other",
}

MENU_BUTTONS = {
    "👤 Profile", "💰 Live Payments", "📋 View Tasks", "🎁 Referral",
    "💳 Withdraw", "📊 Stats", "📣 Promotion", "🆘 Support",
    "💼 Sponsor Panel", "🏠 Main Menu", "🔙 Back to Main Menu",
    "💳 Set/Update Wallet",
}


# ══════════════════════════════════════════════════════════════════
# Styled inline button
# ══════════════════════════════════════════════════════════════════

class StyledButton(InlineKeyboardButton):
    """InlineKeyboardButton with an optional `style` field (Bot API 9.x+)."""

    __slots__ = ("_style",)

    def __init__(self, text: str, style: Optional[str] = None, **kwargs):
        super().__init__(text=text, **kwargs)
        object.__setattr__(self, "_style", style)

    def to_dict(self, recursive: bool = True) -> JSONDict:
        data = super().to_dict(recursive=recursive)
        if self._style:
            data["style"] = self._style
        return data


def _is_menu_button(text: str) -> bool:
    return text.strip() in MENU_BUTTONS


def _gen_ticket_code() -> str:
    suffix = "".join(random.choices(string.digits, k=5))
    return f"SUP-{suffix}"


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    message = update.message

    if not await RateLimitMiddleware.check_support(user.id):
        await message.reply_text("⏳ You've created too many tickets recently. Please wait.")
        return ConversationHandler.END

    buttons = []
    for cat, label in CATEGORIES.items():
        buttons.append([
            StyledButton(label, style="primary", callback_data=f"support_cat:{cat}")
        ])
    buttons.append([
        StyledButton("❌ Cancel", style="danger", callback_data="support_cancel")
    ])

    await message.reply_text(
        "🆘 <b>SUPPORT</b>\n\n"
        f"Our support: {settings.SUPPORT_USERNAME}\n\n"
        "Or create a support ticket below.\n"
        "Select a category:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECT_CATEGORY


# ══════════════════════════════════════════════════════════════════
# State handlers
# ══════════════════════════════════════════════════════════════════

async def support_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data.split(":")[1]
    context.user_data["support_category"] = category
    await query.edit_message_text(
        f"📂 Category: <b>{CATEGORIES.get(category, category)}</b>\n\n"
        "Please enter a brief subject for your ticket:",
        parse_mode="HTML",
    )
    return ENTER_SUBJECT


async def support_enter_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()

    if _is_menu_button(text):
        context.user_data.clear()
        await update.message.reply_text("❌ Support ticket cancelled.")
        return ConversationHandler.END

    subject = text[:256]
    context.user_data["support_subject"] = subject

    await update.message.reply_text("📝 Now describe your issue in detail:")
    return ENTER_MESSAGE


async def support_enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = (update.message.text or "").strip()

    if _is_menu_button(text):
        context.user_data.clear()
        await update.message.reply_text("❌ Support ticket cancelled.")
        return ConversationHandler.END

    message_text = text[:2000]
    category = context.user_data.get("support_category", "OTHER")
    subject = context.user_data.get("support_subject", "No subject")

    try:
        async with get_session() as session:
            async with session.begin():
                from models.support_ticket import SupportTicket, TicketCategory, TicketStatus
                ticket = SupportTicket(
                    ticket_code=_gen_ticket_code(),
                    user_id=user.id,
                    category=TicketCategory(category),
                    subject=subject,
                    message=message_text,
                    status=TicketStatus.OPEN,
                )
                session.add(ticket)
                await session.flush()
                ticket_code = ticket.ticket_code
    except Exception:
        log.exception("Failed to save support ticket", user_id=user.id)
        await update.message.reply_text(
            "❌ Could not save your ticket. Please try again later."
        )
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ <b>Ticket Created!</b>\n\n"
        f"🎫 Ticket: <code>{ticket_code}</code>\n"
        f"📂 Category: {CATEGORIES.get(category, category)}\n"
        f"📋 Subject: {subject}\n\n"
        f"Our team will review and respond soon.\n"
        f"Contact: {settings.SUPPORT_USERNAME}",
        parse_mode="HTML",
    )

    # Notify admin (await directly so we see the result)
    try:
        from services.notification_service import NotificationService
        username = f"@{user.username}" if user.username else "—"

        ok = await NotificationService.notify_admin_critical(
            f"📩 <b>New Support Ticket</b>\n\n"
            f"🎫 Ticket: <code>{ticket_code}</code>\n"
            f"👤 User: <code>{user.id}</code> ({username})\n"
            f"📂 Category: {CATEGORIES.get(category, category)}\n"
            f"📋 Subject: {subject}\n\n"
            f"💬 Message:\n{message_text[:800]}"
        )
        log.info("Support ticket admin notify", ticket=ticket_code, admins_reached=ok)
    except Exception:
        log.exception("Failed to notify admin about support ticket", ticket=ticket_code)

    context.user_data.clear()
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text("❌ Support ticket cancelled.")
        except Exception:
            await update.callback_query.message.reply_text("❌ Support ticket cancelled.")
    else:
        await update.message.reply_text("❌ Support ticket cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════
# Conversation handler
# ══════════════════════════════════════════════════════════════════

def support_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^🆘 Support$"), support_start),
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(support_select_category, pattern=r"^support_cat:"),
                CallbackQueryHandler(support_cancel, pattern=r"^support_cancel$"),
            ],
            ENTER_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_enter_subject),
            ],
            ENTER_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_enter_message),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(support_cancel, pattern=r"^support_cancel$"),
            CommandHandler("cancel", support_cancel),
        ],
        per_message=False,
    )