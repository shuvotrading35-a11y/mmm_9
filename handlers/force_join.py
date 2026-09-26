"""
Force Join Handler — handles the 'Joined - Check' callback.
"""
from pathlib import Path

import structlog
from telegram import Update, InputFile
from telegram.ext import ContextTypes

from database import get_session
from services.force_join_service import ForceJoinService

log = structlog.get_logger(__name__)

# Same banner path as the middleware
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "force_join_banner.jpg"


async def handle_force_join_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User claims to have joined all required channels — re-check."""
    query = update.callback_query
    user = update.effective_user
    await query.answer("⏳ Checking...")

    async with get_session() as session:
        all_joined, missing = await ForceJoinService.check_user_membership(
            bot=context.bot,
            session=session,
            user_id=user.id,
        )

    # ══════════════════════════════════════════════════════════════
    # All joined — send main menu
    # ══════════════════════════════════════════════════════════════
    if all_joined:
        try:
            await query.message.delete()
        except Exception:
            pass

        # Determine sponsor status
        is_sponsor = False
        try:
            async with get_session() as session:
                from services.sponsor_service import SponsorService
                sponsor = await SponsorService.get_sponsor_by_user(session, user.id)
                if sponsor is not None:
                    status_str = (
                        sponsor.status.value if hasattr(sponsor.status, "value")
                        else str(sponsor.status)
                    )
                    is_sponsor = (status_str == "APPROVED")
        except Exception:
            log.exception("Failed to check sponsor status")

        from keyboards.user_keyboards import main_menu_keyboard

        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"✅ <b>Verified!</b>\n\n"
                f"Welcome, <b>{user.first_name}</b>! 👋\n\n"
                f"Use the menu below to start earning."
            ),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_sponsor=is_sponsor),
        )
        return

    # ══════════════════════════════════════════════════════════════
    # Still missing some channels
    # ══════════════════════════════════════════════════════════════
    total = len(missing)
    keyboard = ForceJoinService.build_join_keyboard(missing)

    caption = (
        f"❌ <b>You haven't joined all channels yet.</b>\n\n"
        f"📌 You still need to join <b>{total}</b> channel(s).\n"
        f"👉 Join each one below, then tap <b>✅ Joined - Check</b> again."
    )

    # ── Strategy ──
    # The original message is a photo with caption. So:
    #   1. Try edit_message_caption first (works if it was a photo).
    #   2. If that fails (it was a text message), try edit_message_text.
    #   3. If both fail, send a fresh photo (or text if banner missing).

    # 1. Try editing caption (photo message)
    try:
        await query.edit_message_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return
    except Exception:
        pass

    # 2. Try editing text (plain message)
    try:
        await query.edit_message_text(
            caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return
    except Exception:
        pass

    # 3. Fallback — send a fresh message
    try:
        if BANNER_PATH.exists():
            with open(BANNER_PATH, "rb") as f:
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=InputFile(f, filename="force_join.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        else:
            await context.bot.send_message(
                chat_id=user.id,
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception:
        log.exception("Failed to send force-join retry prompt", user_id=user.id)