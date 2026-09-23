"""
Sponsor Keyboards — ReplyKeyboard (styled) for main menu.
Requires python-telegram-bot>=22.7.
"""
from telegram import ReplyKeyboardMarkup, KeyboardButton


def sponsor_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("➕ Create Campaign", style="primary"),
                KeyboardButton("📋 My Campaigns"),
            ],
            [
                KeyboardButton("💰 Deposit USDT", style="success"),
                KeyboardButton("📊 Analytics"),
            ],
            [
                KeyboardButton("💼 Wallet Info"),
                KeyboardButton("🆘 Support"),
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
                KeyboardButton("🏠 Main Menu"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )