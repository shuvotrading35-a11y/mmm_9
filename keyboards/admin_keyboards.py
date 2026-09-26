"""
Admin Keyboards — ReplyKeyboard (styled) for main menu,
InlineKeyboard for per-item actions.
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

def admin_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                StyledKeyboardButton("👥 Users",      style="primary"),
                StyledKeyboardButton("📋 Campaigns",  style="primary"),
            ],
            [
                StyledKeyboardButton("💼 Sponsors", style="primary"),
                StyledKeyboardButton("💰 Deposits", style="success"),
            ],
            [
                StyledKeyboardButton("💳 Withdrawals", style="success"),
                StyledKeyboardButton("🎁 Referrals",   style="primary"),
            ],
            [
                StyledKeyboardButton("📊 Admin Stats", style="primary"),
                StyledKeyboardButton("📢 Broadcast",   style="primary"),
            ],
            [
                StyledKeyboardButton("📢 Force Join",   style="primary"),
                StyledKeyboardButton("🚫 Banned Users", style="danger"),
            ],
            [
                StyledKeyboardButton("⚙️ Settings",      style="primary"),
                StyledKeyboardButton("🛡 Fraud Monitor", style="danger"),
            ],
            [
                StyledKeyboardButton("📜 Audit Logs", style="primary"),
            ],
            [
                StyledKeyboardButton("🔙 Close Admin Panel", style="danger"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Admin Panel — choose an option...",
    )


def admin_back_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                StyledKeyboardButton("🔙 Back to Admin Panel", style="primary"),
                StyledKeyboardButton("🏠 Main Menu",            style="primary"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                StyledKeyboardButton("❌ Cancel Admin",         style="danger"),
                StyledKeyboardButton("🔙 Back to Admin Panel",  style="primary"),
            ],
        ],
        resize_keyboard=True,
    )


# ══════════════════════════════════════════════════════════════════
# Inline keyboards — per-item actions (need an ID)
# ══════════════════════════════════════════════════════════════════

def user_action_keyboard(user_id: int, status: str) -> InlineKeyboardMarkup:
    """Generic user action keyboard (kept for compatibility)."""
    buttons = [
        [StyledButton(
            "💰 Adjust Balance",
            style="primary",
            callback_data=f"admin:user_balance:{user_id}",
        )],
    ]
    if status != "BANNED":
        buttons.append([StyledButton(
            "🚫 Ban User",
            style="danger",
            callback_data=f"admin:ban:{user_id}",
        )])
    else:
        buttons.append([StyledButton(
            "✅ Unban User",
            style="success",
            callback_data=f"admin:unban:{user_id}",
        )])
    if status == "RESTRICTED":
        buttons.append([StyledButton(
            "✅ Unrestrict",
            style="success",
            callback_data=f"admin:unrestrict:{user_id}",
        )])
    buttons.append([StyledButton(
        "🔙 Back",
        style="primary",
        callback_data="admin:users",
    )])
    return InlineKeyboardMarkup(buttons)


def user_detail_keyboard(user_id: int, status: str) -> InlineKeyboardMarkup:
    """Actions for a single user — shown from user detail view."""
    buttons = [
        [StyledButton(
            "💰 Adjust Balance",
            style="primary",
            callback_data=f"admin:user_balance:{user_id}",
        )],
    ]
    if status != "BANNED":
        buttons.append([StyledButton(
            "🚫 Ban User",
            style="danger",
            callback_data=f"admin:ban:{user_id}",
        )])
    else:
        buttons.append([StyledButton(
            "✅ Unban User",
            style="success",
            callback_data=f"admin:unban:{user_id}",
        )])
    buttons.append([StyledButton(
        "🔙 Back to Users",
        style="primary",
        callback_data="admin:users",
    )])
    return InlineKeyboardMarkup(buttons)


def campaign_action_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []

    if status == "PENDING":
        buttons.append([
            StyledButton("✅ Approve", style="success",
                         callback_data=f"admin:campaign_approve:{campaign_id}"),
            StyledButton("❌ Reject",  style="danger",
                         callback_data=f"admin:campaign_reject:{campaign_id}"),
        ])
    if status == "ACTIVE":
        buttons.append([StyledButton(
            "⏸ Pause",
            style="danger",
            callback_data=f"admin:campaign_pause:{campaign_id}",
        )])
    if status == "PAUSED":
        buttons.append([StyledButton(
            "▶️ Resume",
            style="success",
            callback_data=f"admin:campaign_resume:{campaign_id}",
        )])

    if status != "COMPLETED":
        buttons.append([StyledButton(
            "🗑 Delete (Force)",
            style="danger",
            callback_data=f"admin:campaign_delete:{campaign_id}",
        )])

    buttons.append([StyledButton(
        "🔙 Back",
        style="primary",
        callback_data="admin:campaigns",
    )])
    return InlineKeyboardMarkup(buttons)


def withdrawal_action_keyboard(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            StyledButton("✅ Approve", style="success",
                         callback_data=f"admin:wd_approve:{withdrawal_id}"),
            StyledButton("❌ Reject",  style="danger",
                         callback_data=f"admin:wd_reject:{withdrawal_id}"),
        ],
        [StyledButton("🔙 Back", style="primary", callback_data="admin:withdrawals")],
    ])


def sponsor_action_keyboard(sponsor_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []

    # Add Balance — always available
    buttons.append([StyledButton(
        "💰 Add Balance",
        style="primary",
        callback_data=f"admin:sponsor_add_balance:{sponsor_id}",
    )])

    if status == "PENDING":
        buttons.append([
            StyledButton("✅ Approve", style="success",
                         callback_data=f"admin:sponsor_approve:{sponsor_id}"),
            StyledButton("❌ Reject",  style="danger",
                         callback_data=f"admin:sponsor_reject:{sponsor_id}"),
        ])

    if status == "APPROVED":
        buttons.append([StyledButton(
            "🚫 Suspend",
            style="danger",
            callback_data=f"admin:sponsor_suspend:{sponsor_id}",
        )])

    if status in ("SUSPENDED", "REJECTED"):
        buttons.append([StyledButton(
            "✅ Un-suspend (Reactivate)",
            style="success",
            callback_data=f"admin:sponsor_activate:{sponsor_id}",
        )])

    buttons.append([StyledButton(
        "🔙 Back",
        style="primary",
        callback_data="admin:sponsors",
    )])
    return InlineKeyboardMarkup(buttons)


def deposit_action_keyboard(deposit_id: int, status: str) -> InlineKeyboardMarkup:
    """Action buttons for a specific deposit."""
    buttons = []

    if status == "PENDING":
        buttons.append([
            StyledButton("✅ Approve", style="success",
                         callback_data=f"admin:deposit_approve:{deposit_id}"),
            StyledButton("❌ Reject",  style="danger",
                         callback_data=f"admin:deposit_reject:{deposit_id}"),
        ])

    buttons.append([StyledButton(
        "🔙 Back",
        style="primary",
        callback_data="admin:deposits",
    )])

    return InlineKeyboardMarkup(buttons)


# ══════════════════════════════════════════════════════════════════
# Force Join channel management
# ══════════════════════════════════════════════════════════════════

def force_join_manage_keyboard(channels: list) -> InlineKeyboardMarkup:
    """List all force-join channels with per-item delete buttons."""
    buttons = []
    for ch in channels:
        status_icon = "✅" if ch.get("is_active") else "⏸"
        label = (
            ch.get("title")
            or ch.get("username")
            or str(ch.get("chat_id"))
        )
        buttons.append([
            StyledButton(
                f"{status_icon} {label[:30]}",
                style="primary",
                callback_data=f"admin:fj_view:{ch['id']}",
            ),
            StyledButton(
                "🗑",
                style="danger",
                callback_data=f"admin:fj_delete:{ch['id']}",
            ),
        ])

    buttons.append([StyledButton(
        "➕ Add Channel",
        style="success",
        callback_data="admin:fj_add",
    )])
    buttons.append([StyledButton(
        "🔙 Back to Admin Panel",
        style="primary",
        callback_data="admin:back",
    )])

    return InlineKeyboardMarkup(buttons)


def force_join_confirm_delete_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            StyledButton(
                "✅ Yes, Delete",
                style="danger",
                callback_data=f"admin:fj_delete_confirm:{channel_id}",
            ),
            StyledButton(
                "❌ Cancel",
                style="success",
                callback_data=f"admin:fj_view:{channel_id}",
            ),
        ],
    ])