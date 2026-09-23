"""
Admin Keyboards — inline keyboards for admin panel.
"""
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Users", callback_data="admin:users"),
            InlineKeyboardButton("📋 Campaigns", callback_data="admin:campaigns"),
        ],
        [
            InlineKeyboardButton("💼 Sponsors", callback_data="admin:sponsors"),
            InlineKeyboardButton("💰 Deposits", callback_data="admin:deposits"),
        ],
        [
            InlineKeyboardButton("💳 Withdrawals", callback_data="admin:withdrawals"),
            InlineKeyboardButton("🎁 Referrals", callback_data="admin:referrals"),
        ],
        [
            InlineKeyboardButton("📊 Statistics", callback_data="admin:stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton("🚫 Banned Users", callback_data="admin:banned"),
            InlineKeyboardButton("⚙️ Settings", callback_data="admin:settings"),
        ],
        [
            InlineKeyboardButton("🛡 Fraud Monitor", callback_data="admin:fraud"),
            InlineKeyboardButton("📜 Audit Logs", callback_data="admin:audit"),
        ],
    ])


def user_action_keyboard(user_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("💰 Adjust Balance", callback_data=f"admin:user_balance:{user_id}")],
    ]
    if status not in ("BANNED",):
        buttons.append([InlineKeyboardButton("🚫 Ban User", callback_data=f"admin:ban:{user_id}")])
    else:
        buttons.append([InlineKeyboardButton("✅ Unban User", callback_data=f"admin:unban:{user_id}")])
    if status == "RESTRICTED":
        buttons.append([InlineKeyboardButton("✅ Unrestrict", callback_data=f"admin:unrestrict:{user_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:users")])
    return InlineKeyboardMarkup(buttons)


def campaign_action_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "PENDING":
        buttons.append([
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:campaign_approve:{campaign_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:campaign_reject:{campaign_id}"),
        ])
    if status == "ACTIVE":
        buttons.append([InlineKeyboardButton("⏸ Pause", callback_data=f"admin:campaign_pause:{campaign_id}")])
    if status == "PAUSED":
        buttons.append([InlineKeyboardButton("▶️ Resume", callback_data=f"admin:campaign_resume:{campaign_id}")])
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
    if status == "PENDING":
        buttons.append([
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:sponsor_approve:{sponsor_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:sponsor_reject:{sponsor_id}"),
        ])
    if status == "APPROVED":
        buttons.append([InlineKeyboardButton("🚫 Suspend", callback_data=f"admin:sponsor_suspend:{sponsor_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin:sponsors")])
    return InlineKeyboardMarkup(buttons)
