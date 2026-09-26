"""
Menu message helper — keeps only the latest bot menu message visible
per user, deleting the previous one when a new menu is shown.
Also deletes the user's button-press message (reply keyboard taps)
so the chat stays clean. Commands like /start are preserved.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

log = structlog.get_logger(__name__)


async def send_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
) -> None:
    """
    Send a "menu style" message:
      - If the update is a callback query → try to edit the existing message
        in place (fastest, no deletion).
      - Otherwise: delete the previous menu message for this chat and
        the incoming button-press message, then send a fresh one.
      - The new message id is tracked in context.user_data for next time.
    """
    chat = update.effective_chat
    if chat is None:
        return
    chat_id = chat.id
    key = f"menu_msg_id_{chat_id}"

    # ── 1. Callback query: try to edit in place ──
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
            )
            return
        except Exception:
            # Edit failed (content same, or message type mismatch, or
            # message was a photo). Fall through to delete + send.
            pass

    # ── 2. Delete previous tracked menu message ──
    prev_id = context.user_data.get(key)
    if prev_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception:
            # Already deleted / too old / not found — ignore
            pass

    # ── 3. Delete incoming message (button press only; keep commands) ──
    if update.message:
        txt = (update.message.text or "").strip()
        is_command = txt.startswith("/")
        if not is_command:
            try:
                await update.message.delete()
            except Exception:
                pass

    # ── 4. Send new message ──
    sent = None
    try:
        if update.callback_query:
            sent = await update.callback_query.message.reply_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
            )
        else:
            sent = await update.message.reply_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
            )
    except Exception:
        log.exception("send_menu: failed to send message")
        return

    # ── 5. Track new message id ──
    if sent is not None:
        context.user_data[key] = sent.message_id