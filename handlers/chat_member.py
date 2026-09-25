"""
Chat Member Handler — detect when users leave force-join channels.

Telegram sends `chat_member` updates to a bot that is an admin in a chat.
We use this to notify users who leave a required channel.

⚠️ The bot MUST be an admin in the channel with the
   "Manage Chat" (can_manage_chat) permission.
"""
import structlog

from telegram import (
    Update,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from database import get_session

log = structlog.get_logger(__name__)


def _was_member(status: str) -> bool:
    return status in ("member", "administrator", "creator", "restricted")


def _is_member(status: str) -> bool:
    return status in ("member", "administrator", "creator")


def _build_rejoin_keyboard(fj) -> InlineKeyboardMarkup:
    buttons = []
    url = None
    if fj.invite_url:
        url = fj.invite_url
    elif fj.username:
        url = f"https://t.me/{fj.username.lstrip('@')}"

    if url:
        buttons.append([InlineKeyboardButton("📢 Re-join Channel", url=url)])

    buttons.append([InlineKeyboardButton(
        "✅ I've Joined — Check Again",
        callback_data="force_join_check",
    )])
    return InlineKeyboardMarkup(buttons)


async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle chat_member updates — notify users who left a force-join channel."""
    cmu: ChatMemberUpdated = update.chat_member
    if not cmu:
        return

    chat = cmu.chat
    user = cmu.new_chat_member.user
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status

    # Only care about departures
    if not (_was_member(old_status) and not _is_member(new_status)):
        return

    # Skip bots
    if user.is_bot:
        return

    log.info(
        "User left channel",
        user_id=user.id,
        chat_id=chat.id,
        chat_title=chat.title,
        old_status=old_status,
        new_status=new_status,
    )

    # Is this chat actually a force-join channel?
    from sqlalchemy import select
    from models.force_join import ForceJoinChannel

    async with get_session() as session:
        result = await session.execute(
            select(ForceJoinChannel).where(
                ForceJoinChannel.chat_id == chat.id,
                ForceJoinChannel.is_active == True,
            )
        )
        fj = result.scalar_one_or_none()

    if not fj:
        return  # Not a force-join channel — ignore

    # Notify the user
    channel_label = f"@{fj.username}" if fj.username else (chat.title or "our channel")
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"❌ <b>Channel Left Detected</b>\n\n"
                f"You have left <b>{channel_label}</b>.\n\n"
                f"To keep using this bot, please re-join the channel:\n"
                f"After joining, tap the button below to continue."
            ),
            parse_mode="HTML",
            reply_markup=_build_rejoin_keyboard(fj),
        )
    except Exception as e:
        log.warning(
            "Could not notify user about force-join departure",
            user_id=user.id,
            error=str(e),
        )