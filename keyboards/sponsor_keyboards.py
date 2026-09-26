"""
Sponsor Keyboards — ReplyKeyboard (styled) for main menu,
InlineKeyboard for per-campaign actions.
Requires python-telegram-bot>=22.7.
"""
from typing import Optional

from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram._utils.types import JSONDict


# ══════════════════════════════════════════════════════════════════
# Styled buttons
# ══════════════════════════════════════════════════════════════════
# NOTE: move these two classes into a shared module
# (e.g. keyboards/style.py) and import them in every keyboard file.

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


class StyledKeyboardButton(KeyboardButton):
    """KeyboardButton with an optional `style` field for reply keyboards."""

    __slots__ = ("_style",)

    def __init__(self, text: str, style: Optional[str] = None, **kwargs):
        super().__init__(text=text, **kwargs)
        object.__setattr__(self, "_style", style)

    def to_dict(self, recursive: bool = True) -> JSONDict:
        data = super().to_dict(recursive=recursive)
        if self._style:
            data["style"] = self._style
        return data


# ══════════════════════════════════════════════════════════════════
# Reply keyboards — main navigation
# ══════════════════════════════════════════════════════════════════

def sponsor_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                StyledKeyboardButton("➕ Create Campaign", style="success"),
                StyledKeyboardButton("📋 My Campaigns",   style="primary"),
            ],
            [
                StyledKeyboardButton("💰 Deposit USDT", style="success"),
                StyledKeyboardButton("📊 Analytics",    style="primary"),
            ],
            [
                StyledKeyboardButton("💼 Wallet Info",      style="primary"),
                StyledKeyboardButton("🆘 Sponsor Support",  style="primary"),
            ],
            [
                StyledKeyboardButton("🔙 Back to Main Menu", style="danger"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Sponsor Panel — choose an option...",
    )


def sponsor_task_type_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [StyledKeyboardButton("📢 Channel Join",       style="primary")],
            [StyledKeyboardButton("👥 Group Join",         style="primary")],
            [StyledKeyboardButton("📢👥 Channel + Group",  style="success")],
            [StyledKeyboardButton("❌ Cancel Sponsor",     style="danger")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Choose task type...",
    )


def sponsor_duration_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                StyledKeyboardButton("1 Day",  style="primary"),
                StyledKeyboardButton("3 Days", style="primary"),
            ],
            [
                StyledKeyboardButton("7 Days",  style="primary"),
                StyledKeyboardButton("30 Days", style="primary"),
            ],
            [StyledKeyboardButton("❌ Cancel Sponsor", style="danger")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Choose duration...",
    )


def sponsor_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[StyledKeyboardButton("❌ Cancel Sponsor", style="danger")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def sponsor_back_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                StyledKeyboardButton("🔙 Back to Sponsor Panel", style="primary"),
                StyledKeyboardButton("🏠 Main Menu",             style="primary"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ══════════════════════════════════════════════════════════════════
# Inline keyboards — per-campaign actions
# ══════════════════════════════════════════════════════════════════

def campaign_actions_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    """Action buttons for a specific campaign."""
    buttons = []
    s = (status or "").upper()

    if s == "PENDING_FUNDING":
        buttons.append([StyledButton(
            "💰 Fund Campaign",
            style="success",
            callback_data=f"sponsor:fund:{campaign_id}",
        )])

    if s == "ACTIVE":
        buttons.append([StyledButton(
            "⏸ Pause",
            style="danger",
            callback_data=f"sponsor:pause:{campaign_id}",
        )])

    if s == "PAUSED":
        buttons.append([StyledButton(
            "▶️ Resume",
            style="success",
            callback_data=f"sponsor:resume:{campaign_id}",
        )])

    buttons.append([StyledButton(
        "📊 Analytics",
        style="primary",
        callback_data=f"sponsor:analytics:{campaign_id}",
    )])

    # Delete button — not available for completed campaigns
    if s != "COMPLETED":
        buttons.append([StyledButton(
            "🗑 Delete Campaign",
            style="danger",
            callback_data=f"sponsor:delete_prompt:{campaign_id}",
        )])

    buttons.append([StyledButton(
        "🔙 Back",
        style="primary",
        callback_data="sponsor:campaigns",
    )])

    return InlineKeyboardMarkup(buttons)


def campaign_delete_confirm_keyboard(campaign_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard before deleting a campaign."""
    return InlineKeyboardMarkup([
        [
            StyledButton(
                "✅ Yes, Delete",
                style="danger",
                callback_data=f"sponsor:delete_confirm:{campaign_id}",
            ),
            StyledButton(
                "❌ Cancel",
                style="success",
                callback_data=f"sponsor:campaign_detail:{campaign_id}",
            ),
        ],
    ])


def deposit_submitted_keyboard() -> InlineKeyboardMarkup:
    """After tx hash submitted."""
    return InlineKeyboardMarkup([
        [StyledButton("🔙 Back to Panel", style="primary", callback_data="sponsor:back")],
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