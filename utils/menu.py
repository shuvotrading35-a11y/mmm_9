"""
Single-message menu helper.

Keeps only ONE menu message per chat:
  • Reply-keyboard taps → delete previous menu + user's tap message, send new
  • Inline callbacks → try to edit in place (fast, no flicker)
  • Supports both text and photo messages

Usage:
    await send_menu(update, context, text="...", reply_markup=kb)
    await send_menu(update, context, text="...", reply_markup=kb,
                    photo_path="assets/task_banner.jpg")
"""
from pathlib import Path

import structlog
from telegram import Update, InputFile
from telegram.ext import ContextTypes

log = structlog.get_logger(__name__)


def _delete_key(chat_id: int) -> str:
    return f"menu_msg_id_{chat_id}"


async def _try_delete(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        # Already gone, too old, or not ours — ignore
        pass


async def send_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
    photo_path: str | Path | None = None,
) -> None:
    """Send a menu message, auto-deleting the previous one."""
    chat = update.effective_chat
    if chat is None:
        return
    chat_id = chat.id
    key = _delete_key(chat_id)
    bot = context.bot

    has_photo = bool(photo_path) and Path(photo_path).exists()

    # ── 1. Callback: try to edit in place (text or caption) ──
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
            )
            return
        except Exception:
            pass
        try:
            await update.callback_query.edit_message_caption(
                caption=text, parse_mode=parse_mode, reply_markup=reply_markup,
            )
            return
        except Exception:
            pass
        # Fall through → delete + send fresh

    # ── 2. Delete previous tracked menu message ──
    prev_id = context.user_data.get(key)
    if prev_id:
        await _try_delete(bot, chat_id, prev_id)

    # ── 3. Delete user's incoming message (button tap only; keep commands) ──
    if update.message:
        txt = (update.message.text or "").strip()
        if not txt.startswith("/"):
            try:
                await update.message.delete()
            except Exception:
                pass

    # ── 4. Send the new message ──
    sent = None
    try:
        if has_photo:
            with open(photo_path, "rb") as f:
                if update.callback_query:
                    sent = await update.callback_query.message.reply_photo(
                        photo=InputFile(f, filename=Path(photo_path).name),
                        caption=text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                else:
                    sent = await update.message.reply_photo(
                        photo=InputFile(f, filename=Path(photo_path).name),
                        caption=text,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
        else:
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

    # ── 5. Track the new message id ──
    if sent is not None:
        context.user_data[key] = sent.message_id