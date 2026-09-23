"""
Promotion Handler — show how to become a sponsor and promote campaigns.
"""
from telegram import Update
from telegram.ext import ContextTypes
from config import settings


async def handle_promotion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        f"📣 <b>ADVERTISE WITH US</b>\n\n"
        f"Reach thousands of active Telegram users through our task network!\n\n"
        f"━━━━━━ HOW IT WORKS ━━━━━━\n"
        f"1️⃣ Register as a Sponsor\n"
        f"2️⃣ Get approved by our team\n"
        f"3️⃣ Deposit USDT (BSC) to your account\n"
        f"4️⃣ Create a campaign (channel join, group join, etc.)\n"
        f"5️⃣ Users complete your task and you gain real members\n\n"
        f"━━━━━━ BENEFITS ━━━━━━\n"
        f"✅ Real, verified Telegram members\n"
        f"✅ Pay only for completed tasks\n"
        f"✅ Full analytics dashboard\n"
        f"✅ Campaign control (pause, resume, cancel)\n"
        f"✅ Unused budget fully refundable\n\n"
        f"━━━━━━ PRICING ━━━━━━\n"
        f"💰 Minimum reward per user: {settings.TASK_MIN_REWARD} USDT\n"
        f"💰 Maximum reward per user: {settings.TASK_MAX_REWARD} USDT\n"
        f"💵 Minimum deposit: {settings.SPONSOR_MIN_DEPOSIT} USDT\n\n"
        f"📩 Contact us: {settings.SUPPORT_USERNAME}\n"
        f"Or use 🆘 Support to apply as a sponsor."
    )
    await update.message.reply_text(text, parse_mode="HTML")
