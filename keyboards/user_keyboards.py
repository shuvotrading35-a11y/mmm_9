"""
User Keyboards — ReplyKeyboard and InlineKeyboard builders for regular users.
"""
from typing import Optional

from telegram import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram._utils.types import JSONDict


# ══════════════════════════════════════════════════════════════════
# Styled buttons (Bot-API "style" passthrough)
# ══════════════════════════════════════════════════════════════════

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
# Reply keyboards
# ══════════════════════════════════════════════════════════════════

def main_menu_keyboard(is_sponsor: bool = False) -> ReplyKeyboardMarkup:
    """Main menu ReplyKeyboard with styles."""
    keyboard = [
        [
            StyledKeyboardButton("👤 Profile", style="primary"),
            StyledKeyboardButton("💰 Live Payments", style="success"),
        ],
        [
            StyledKeyboardButton("📋 View Tasks", style="primary"),
            StyledKeyboardButton("🎁 Referral", style="primary"),
        ],
        [
            StyledKeyboardButton("💳 Withdraw", style="success"),
            StyledKeyboardButton("📊 Stats", style="primary"),
        ],
        [
            StyledKeyboardButton("📣 Promotion", style="primary"),
            StyledKeyboardButton("🆘 Support", style="primary"),
        ],
    ]
    if is_sponsor:
        keyboard.append([
            StyledKeyboardButton("💼 Sponsor Panel", style="primary"),
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
            [StyledKeyboardButton("💳 Set/Update Wallet", style="success")],
            [StyledKeyboardButton("🔙 Back to Main Menu", style="primary")],
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
                StyledKeyboardButton("❌ Cancel", style="danger"),
                StyledKeyboardButton("🏠 Main Menu", style="primary"),
            ],
        ],
        resize_keyboard=True,
    )


def user_back_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with just a Back-to-Main button."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [StyledKeyboardButton("🏠 Main Menu", style="primary")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ══════════════════════════════════════════════════════════════════
# Inline keyboards
# ══════════════════════════════════════════════════════════════════

def task_keyboard(campaign_id: int, join_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [StyledButton("🔗 JOIN", style="primary", url=join_url)],
        [
            StyledButton("✅ DONE", style="success", callback_data=f"task_done:{campaign_id}"),
            StyledButton("❌ SKIP", style="danger",  callback_data=f"task_skip:{campaign_id}"),
        ],
        [StyledButton("➡️ NEXT TASK", style="primary", callback_data="task_next")],
    ])


def task_no_join_keyboard(campaign_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            StyledButton("✅ DONE", style="success", callback_data=f"task_done:{campaign_id}"),
            StyledButton("❌ SKIP", style="danger",  callback_data=f"task_skip:{campaign_id}"),
        ],
        [StyledButton("➡️ NEXT TASK", style="primary", callback_data="task_next")],
    ])


def withdraw_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            StyledButton("✅ CONFIRM WITHDRAWAL", style="success", callback_data="withdraw_confirm"),
            StyledButton("❌ CANCEL",            style="danger",  callback_data="withdraw_cancel"),
        ]
    ])


def live_payments_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [StyledButton("🔄 Refresh", style="primary", callback_data="live_refresh")]
    ])


def cancel_keyboard(callback_data: str = "cancel") -> InlineKeyboardMarkup:
    """Inline keyboard with a Cancel button."""
    return InlineKeyboardMarkup([
        [StyledButton("❌ Cancel", style="danger", callback_data=callback_data)]
    ])


def back_keyboard(callback_data: str = "back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [StyledButton("🔙 Back", style="primary", callback_data=callback_data)]
    ])