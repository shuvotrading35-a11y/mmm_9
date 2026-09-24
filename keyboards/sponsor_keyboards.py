"""
Sponsor Keyboards — ReplyKeyboard (styled) for main menu,
InlineKeyboard for per-campaign actions.
Requires python-telegram-bot>=22.7.
"""
from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


# ══════════════════════════════════════════════════════════════════
# Reply keyboards — main navigation
# ══════════════════════════════════════════════════════════════════

def sponsor_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("➕ Create Campaign", style="primary"),
                KeyboardButton("📋 My Campaigns", style="primary"),
            ],
            [
                KeyboardButton("💰 Deposit USDT", style="success"),
                KeyboardButton("📊 Analytics", style="primary"),
            ],
            [
                KeyboardButton("💼 Wallet Info", style="primary"),
                KeyboardButton("🆘 Sponsor Support", style="primary"),
            ],
            [
                KeyboardButton("🔙 Back to Main Menu", style="danger"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Sponsor Panel — choose an option...",
    )


def sponsor_task_type_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📢 Channel Join", style="primary")],
            [KeyboardButton("👥 Group Join", style="primary")],
            [KeyboardButton("🤖 Bot Start", style="primary")],
            [KeyboardButton("📢👥 Channel + Group", style="primary")],
            [KeyboardButton("❌ Cancel Sponsor", style="danger")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Choose task type...",
    )


def sponsor_duration_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("1 Day", style="primary"),
                KeyboardButton("3 Days", style="primary"),
            ],
            [
                KeyboardButton("7 Days", style="primary"),
                KeyboardButton("30 Days", style="primary"),
            ],
            [KeyboardButton("❌ Cancel Sponsor", style="danger")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Choose duration...",
    )


def sponsor_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("❌ Cancel Sponsor", style="danger")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def sponsor_back_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("🔙 Back to Sponsor Panel", style="primary"),
                KeyboardButton("🏠 Main Menu", style="primary"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ══════════════════════════════════════════════════════════════════
# Inline keyboards — per-campaign actions (need campaign_id)
# (style parameter doesn't apply to InlineKeyboardButton)
# ══════════════════════════════════════════════════════════════════

def campaign_actions_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    """Action buttons for a specific campaign."""
    buttons = []

    status_upper = (status or "").upper()

    if status_upper == "PENDING_FUNDING":
        buttons.append([InlineKeyboardButton(
            "💰 Fund Campaign",
            callback_data=f"sponsor:fund:{campaign_id}"
        )])

    if status_upper == "ACTIVE":
        buttons.append([InlineKeyboardButton(
            "⏸ Pause",
            callback_data=f"sponsor:pause:{campaign_id}"
        )])

    if status_upper == "PAUSED":
        buttons.append([InlineKeyboardButton(
            "▶️ Resume",
            callback_data=f"sponsor:resume:{campaign_id}"
        )])

    buttons.append([InlineKeyboardButton(
        "📊 Analytics",
        callback_data=f"sponsor:analytics:{campaign_id}"
    )])

    buttons.append([InlineKeyboardButton(
        "🔙 Back",
        callback_data="sponsor:campaigns"
    )])

    return InlineKeyboardMarkup(buttons)


def deposit_submitted_keyboard() -> InlineKeyboardMarkup:
    """After tx hash submitted."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Panel", callback_data="sponsor:back")],
    ])


# ══════════════════════════════════════════════════════════════════
# Legacy / compatibility aliases
# ══════════════════════════════════════════════════════════════════

def sponsor_main_keyboard() -> ReplyKeyboardMarkup:
    """Alias — old name kept for compatibility."""
    return sponsor_main_reply_keyboard()


def task_type_keyboard() -> ReplyKeyboardMarkup:
    """Alias — old name kept for compatibility."""
    return sponsor_task_type_reply_keyboard()


def duration_keyboard() -> ReplyKeyboardMarkup:
    """Alias — old name kept for compatibility."""
    return sponsor_duration_reply_keyboard()