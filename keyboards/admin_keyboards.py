"""
Admin Keyboards — ReplyKeyboard (styled) for main menu,
InlineKeyboard for per-item actions.
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

def admin_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("👥 Users", style="primary"),
                KeyboardButton("📋 Campaigns", style="primary"),
            ],
            [
                KeyboardButton("💼 Sponsors", style="primary"),
                KeyboardButton("💰 Deposits", style="success"),
            ],
            [
                KeyboardButton("💳 Withdrawals", style="success"),
                KeyboardButton("🎁 Referrals", style="primary"),
            ],
            [
                KeyboardButton("📊 Admin Stats", style="primary"),
                KeyboardButton("📢 Broadcast", style="primary"),
            ],
            [
                KeyboardButton("🚫 Banned Users", style="danger"),
                KeyboardButton("⚙️ Settings", style="primary"),
            ],
            [
                KeyboardButton("🛡 Fraud Monitor", style="danger"),
                KeyboardButton("📜 Audit Logs"),
            ],
            [
                KeyboardButton("🔙 Close Admin Panel", style="danger"),
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
                KeyboardButton("🔙 Back to Admin Panel", style="primary"),
                KeyboardButton("🏠 Main Menu", style="primary"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton("❌ Cancel Admin", style="danger"),
                KeyboardButton("🔙 Back to Admin Panel", style="primary"),
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
        [InlineKeyboardButton("💰 Adjust Balance", callback_data=f"admin:user_balance:{user_id}")],
    ]
    if status != "BANNED":
        buttons.append([InlineKeyboardButton("🚫 Ban User", callback_data=f"admin:ban:{user_id}")])
    else:
        buttons.append([InlineKeyboardButton("✅ Unban User", callback_data=f"admin:unban:{user_id}")])
    if status == "RESTRICTED":
        buttons.append([InlineKeyboardButton("✅ Unrestrict", callback_data=f"admin:unrestrict:{user_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:users")])
    return InlineKeyboardMarkup(buttons)


def user_detail_keyboard(user_id: int, status: str) -> InlineKeyboardMarkup:
    """Actions for a single user — shown from user detail view."""
    buttons = [
        [InlineKeyboardButton("💰 Adjust Balance", callback_data=f"admin:user_balance:{user_id}")],
    ]
    if status != "BANNED":
        buttons.append([InlineKeyboardButton("🚫 Ban User", callback_data=f"admin:ban:{user_id}")])
    else:
        buttons.append([InlineKeyboardButton("✅ Unban User", callback_data=f"admin:unban:{user_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back to Users", callback_data="admin:users")])
    return InlineKeyboardMarkup(buttons)


def campaign_action_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []

    if status == "PENDING":
        buttons.append([
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:campaign_approve:{campaign_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:campaign_reject:{campaign_id}"),
        ])
    if status == "ACTIVE":
        buttons.append([InlineKeyboardButton(
            "⏸ Pause", callback_data=f"admin:campaign_pause:{campaign_id}"
        )])
    if status == "PAUSED":
        buttons.append([InlineKeyboardButton(
            "▶️ Resume", callback_data=f"admin:campaign_resume:{campaign_id}"
        )])

    if status != "COMPLETED":
        buttons.append([InlineKeyboardButton(
            "🗑 Delete (Force)",
            callback_data=f"admin:campaign_delete:{campaign_id}",
        )])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:campaigns")])
    return InlineKeyboardMarkup(buttons)


def withdrawal_action_keyboard(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:wd_approve:{withdrawal_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:wd_reject:{withdrawal_id}"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin:withdrawals")],
    ])


def sponsor_action_keyboard(sponsor_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []

    buttons.append([InlineKeyboardButton(
        "💰 Add Balance",
        callback_data=f"admin:sponsor_add_balance:{sponsor_id}",
    )])

    if status == "PENDING":
        buttons.append([
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:sponsor_approve:{sponsor_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:sponsor_reject:{sponsor_id}"),
        ])
    if status == "APPROVED":
        buttons.append([InlineKeyboardButton(
            "🚫 Suspend", callback_data=f"admin:sponsor_suspend:{sponsor_id}"
        )])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:sponsors")])
    return InlineKeyboardMarkup(buttons)


def deposit_action_keyboard(deposit_id: int, status: str) -> InlineKeyboardMarkup:
    """Action buttons for a specific deposit."""
    buttons = []

    if status == "PENDING":
        buttons.append([
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:deposit_approve:{deposit_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:deposit_reject:{deposit_id}"),
        ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:deposits")])

    return InlineKeyboardMarkup(buttons)