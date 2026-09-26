"""
User Keyboards — ReplyKeyboard and InlineKeyboard builders for regular users.
"""
from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


# ══════════════════════════════════════════════════════════════════
# Reply keyboards
# ══════════════════════════════════════════════════════════════════

def main_menu_keyboard(is_sponsor: bool = False) -> ReplyKeyboardMarkup:
    """Main menu ReplyKeyboard with styles."""
    keyboard = [
        [
            KeyboardButton("👤 Profile", style="primary"),
            KeyboardButton("💰 Live Payments", style="success"),
        ],
        [
            KeyboardButton("📋 View Tasks", style="primary"),
            KeyboardButton("🎁 Referral", style="primary"),
        ],
        [
            KeyboardButton("💳 Withdraw", style="success"),
            KeyboardButton("📊 Stats", style="primary"),
        ],
        [
            KeyboardButton("📣 Promotion", style="primary"),
            KeyboardButton("🆘 Support", style="primary"),
        ],
    ]
    if is_sponsor:
        keyboard.append([
            KeyboardButton("💼 Sponsor Panel", style="primary"),
        ])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option...",
    )


def profile_keyboard() -> ReplyKeyboardMarkup:
    """Profile screen's own reply keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("💳 Set/Update Wallet", style="success")],
            [KeyboardButton("🔙 Back to Main Menu", style="primary")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option...",
    )


def user_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with just a Cancel button (for input steps)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("❌ Cancel", style="danger"),
                KeyboardButton("🏠 Main Menu", style="primary"),
            ],
        ],
        resize_keyboard=True,
    )


def user_back_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with just a Back-to-Main button."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🏠 Main Menu", style="primary")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ══════════════════════════════════════════════════════════════════
# Inline keyboards
# ══════════════════════════════════════════════════════════════════

def task_keyboard(campaign_id: int, join_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 JOIN", url=join_url)],
        [
            InlineKeyboardButton("✅ DONE", callback_data=f"task_done:{campaign_id}"),
            InlineKeyboardButton("❌ SKIP", callback_data=f"task_skip:{campaign_id}"),
        ],
        [InlineKeyboardButton("➡️ NEXT TASK", callback_data="task_next")],
    ])


def task_no_join_keyboard(campaign_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ DONE", callback_data=f"task_done:{campaign_id}"),
            InlineKeyboardButton("❌ SKIP", callback_data=f"task_skip:{campaign_id}"),
        ],
        [InlineKeyboardButton("➡️ NEXT TASK", callback_data="task_next")],
    ])


def withdraw_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ CONFIRM WITHDRAWAL", callback_data="withdraw_confirm"),
            InlineKeyboardButton("❌ CANCEL", callback_data="withdraw_cancel"),
        ]
    ])


def live_payments_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="live_refresh")]
    ])


def cancel_keyboard(callback_data: str = "cancel") -> InlineKeyboardMarkup:
    """Inline keyboard with a Cancel button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=callback_data)]
    ])


def back_keyboard(callback_data: str = "back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data=callback_data)]
    ])