"""
Sponsor Keyboards — inline keyboards for sponsor panel.
"""
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def sponsor_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Create Campaign", callback_data="sponsor:create_campaign"),
            InlineKeyboardButton("📋 My Campaigns", callback_data="sponsor:campaigns"),
        ],
        [
            InlineKeyboardButton("💰 Deposit USDT", callback_data="sponsor:deposit"),
            InlineKeyboardButton("📊 Analytics", callback_data="sponsor:analytics"),
        ],
        [
            InlineKeyboardButton("💼 Wallet Info", callback_data="sponsor:wallet"),
            InlineKeyboardButton("🆘 Support", callback_data="sponsor:support"),
        ],
    ])


def task_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel Join", callback_data="sponsor:type:CHANNEL_JOIN")],
        [InlineKeyboardButton("👥 Group Join", callback_data="sponsor:type:GROUP_JOIN")],
        [InlineKeyboardButton("🤖 Bot Start", callback_data="sponsor:type:BOT_START")],
        [InlineKeyboardButton("📢👥 Channel + Group", callback_data="sponsor:type:CHANNEL_GROUP_JOIN")],
        [InlineKeyboardButton("❌ Cancel", callback_data="sponsor:cancel")],
    ])


def duration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 Day", callback_data="sponsor:duration:1"),
            InlineKeyboardButton("3 Days", callback_data="sponsor:duration:3"),
        ],
        [
            InlineKeyboardButton("7 Days", callback_data="sponsor:duration:7"),
            InlineKeyboardButton("30 Days", callback_data="sponsor:duration:30"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="sponsor:cancel")],
    ])


def campaign_actions_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "PENDING_FUNDING":
        buttons.append([InlineKeyboardButton(
            "💰 Fund Campaign", callback_data=f"sponsor:fund:{campaign_id}"
        )])
    if status == "ACTIVE":
        buttons.append([InlineKeyboardButton(
            "⏸ Pause", callback_data=f"sponsor:pause:{campaign_id}"
        )])
    if status == "PAUSED":
        buttons.append([InlineKeyboardButton(
            "▶️ Resume", callback_data=f"sponsor:resume:{campaign_id}"
        )])
    buttons.append([InlineKeyboardButton(
        "📊 Analytics", callback_data=f"sponsor:analytics:{campaign_id}"
    )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="sponsor:campaigns")])
    return InlineKeyboardMarkup(buttons)


def deposit_submitted_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Panel", callback_data="sponsor:back")],
    ])
