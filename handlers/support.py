"""
Support Handler — ticket creation conversation.
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


# ══════════════════════════════════════════════════════════════════
# Styled button
# ══════════════════════════════════════════════════════════════════
# NOTE: move to keyboards/style.py and import everywhere.

class StyledButton(InlineKeyboardButton):
    """InlineKeyboardButton with an optional `style` field."""

    __slots__ = ("_style",)

    def __init__(self, text: str, style: Optional[str] = None, **kwargs):
        super().__init__(text=text, **kwargs)
        object.__setattr__(self, "_style", style)

    def to_dict(self, recursive: bool = True) -> JSONDict:
        data = super().to_dict(recursive=recursive)
        if self._style:
            data["style"] = self._style
        return data


def _gen_ticket_code() -> str:
    suffix = "".join(random.choices(string.digits, k=5))
    return f"SUP-{suffix}"


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    message = update.message

    if not await RateLimitMiddleware.check_support(user.id):
        await message.reply_text("⏳ You've created too many tickets recently. Please wait.")
        return ConversationHandler.END

    buttons = [
        [StyledButton(label, style="primary", callback_data=f"support_cat:{cat}")]
        for cat, label in CATEGORIES.items()
    ]
    buttons.append([StyledButton("❌ Cancel", style="danger", callback_data="support_cancel")])

    await message.reply_text(
        "🆘 <b>SUPPORT</b>\n\n"
        f"Our support: {settings.SUPPORT_USERNAME}\n\n"
        "Or create a support ticket below.\n"
        "Select a category:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return SELECT_CATEGORY


async def support_select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data.split(":")[1]
    context.user_data["support_category"] = category
    await query.edit_message_text(
        f"📂 Category: <b>{CATEGORIES[category]}</b>\n\n"
        "Please enter a brief subject for your ticket:",
        parse_mode="HTML",
    )
    return ENTER_SUBJECT


async def support_enter_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    subject = update.message.text.strip()[:256]
    context.user_data["support_subject"] = subject
    await update.message.reply_text(
        "📝 Now describe your issue in detail:"
    )
    return ENTER_MESSAGE


async def support_enter_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    message_text = update.message.text.strip()[:2000]
    category = context.user_data.get("support_category", "OTHER")
    subject = context.user_data.get("support_subject", "No subject")

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

    await update.message.reply_text(
        f"✅ <b>Ticket Created!</b>\n\n"
        f"🎫 Ticket: <code>{ticket_code}</code>\n"
        f"📂 Category: {CATEGORIES.get(category, category)}\n"
        f"📋 Subject: {subject}\n\n"
        f"Our team will review and respond soon.\n"
        f"Contact: {settings.SUPPORT_USERNAME}",
        parse_mode="HTML",
    )

    # Notify admin
    from services.notification_service import NotificationService
    asyncio.create_task(
        NotificationService.notify_admin_critical(
            f"📩 New Support Ticket {ticket_code}\n"
            f"User: {user.id} (@{user.username})\n"
            f"Category: {category}\n"
            f"Subject: {subject}"
        )
    )

    context.user_data.clear()
    return ConversationHandler.END


async def support_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Support ticket cancelled.")
    else:
        await update.message.reply_text("❌ Support ticket cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def support_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^🆘 Support$"), support_start),
        ],
        states={
            SELECT_CATEGORY: [
                CallbackQueryHandler(support_select_category, pattern=r"^support_cat:"),
                CallbackQueryHandler(support_cancel, pattern="^support_cancel$"),
            ],
            ENTER_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_enter_subject),
            ],
            ENTER_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_enter_message),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(support_cancel, pattern="^support_cancel$"),
            CommandHandler("cancel", support_cancel),
        ],
        per_message=False,
    )