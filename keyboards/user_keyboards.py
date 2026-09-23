"""
User Keyboards — ReplyKeyboard and InlineKeyboard builders for regular users.
"""
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard(is_sponsor: bool = False) -> ReplyKeyboardMarkup:
    """Main menu ReplyKeyboard."""
    buttons = [
        ["👤 Profile", "💰 Live Payments"],
        ["📋 View Tasks", "🎁 Referral"],
        ["💳 Withdraw", "📊 Statistics"],
        ["📣 Promotion", "🆘 Support"],
    ]
    if is_sponsor:
        buttons.append(["💼 Sponsor Panel"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def task_keyboard(campaign_id: int, join_url: str) -> InlineKeyboardMarkup:
    """Task action buttons."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 JOIN", url=join_url)],
        [
            InlineKeyboardButton(f"✅ DONE", callback_data=f"task_done:{campaign_id}"),
            InlineKeyboardButton("❌ SKIP", callback_data=f"task_skip:{campaign_id}"),
        ],
        [InlineKeyboardButton("➡️ NEXT TASK", callback_data="task_next")],
    ])


def task_no_join_keyboard(campaign_id: int) -> InlineKeyboardMarkup:
    """Task buttons when no join URL is available (BOT_START / CUSTOM)."""
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=callback_data)]
    ])


def back_keyboard(callback_data: str = "back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data=callback_data)]
    ])
