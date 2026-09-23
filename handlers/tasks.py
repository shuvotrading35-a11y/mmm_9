"""
Tasks Handler — browse tasks, verify completion, skip.
"""
import asyncio
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import get_session
from keyboards.user_keyboards import task_keyboard, task_no_join_keyboard, main_menu_keyboard
from middlewares.rate_limit_middleware import RateLimitMiddleware
from services.task_service import TaskService
from services.verification_service import VerificationService, FailureReason
from services.reward_service import RewardService
from services.notification_service import NotificationService
from utils.decimal_utils import fmt_usdt
from utils.time_utils import time_until

log = structlog.get_logger(__name__)


def _build_task_text(campaign) -> str:
    from models.campaign import TaskType
    task_label = {
        TaskType.CHANNEL_JOIN: "Join Telegram Channel",
        TaskType.GROUP_JOIN: "Join Telegram Group",
        TaskType.BOT_START: "Start Telegram Bot",
        TaskType.CHANNEL_GROUP_JOIN: "Join Channel & Group",
        TaskType.FORCE_JOIN: "Join Required Channel",
        TaskType.CUSTOM: "Custom Task",
    }.get(campaign.task_type, "Complete Task")

    target = f"@{campaign.telegram_username}" if campaign.telegram_username else f"ID: {campaign.telegram_chat_id}"
    budget_remaining = campaign.total_budget - campaign.spent_budget

    return (
        f"🔗 <b>TELEGRAM TASK INFO #{campaign.id}</b>\n\n"
        f"📌 Task:  {task_label}\n"
        f"📢 Target: {target}\n\n"
        f"📊 Completed: {campaign.completed_count:,} / {campaign.completion_limit:,}\n"
        f"🎁 Reward: <b>{fmt_usdt(campaign.reward_per_user)} USDT</b>\n"
        f"💰 Budget Remaining: <b>{fmt_usdt(budget_remaining)} USDT</b>\n"
        f"⏳ Expires: {time_until(campaign.expires_at)}\n"
        f"🟢 Status: ACTIVE\n\n"
        f"⚠️ Join the target below, then press DONE to verify and claim your reward."
    )


async def handle_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the next available task to the user."""
    user = update.effective_user
    message = update.message or update.callback_query.message

    async with get_session() as session:
        # Force-join check
        from middlewares.force_join_middleware import ForceJoinMiddleware
        if update.message:
            passed = await ForceJoinMiddleware.check(update, context)
            if not passed:
                return

        # Ban check
        from middlewares.ban_middleware import BanMiddleware
        if await BanMiddleware.check(update, context):
            return

        campaign = await TaskService.get_next_task(session, user.id)
        if not campaign:
            count = 0
        else:
            await TaskService.record_view(session, campaign.id)
            count = await TaskService.get_available_tasks_count(session, user.id)

    if not campaign:
        text = (
            "📋 <b>No Tasks Available</b>\n\n"
            "You've completed all available tasks or there are no active campaigns right now.\n\n"
            "Check back later — new tasks are added regularly! 🚀"
        )
        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        else:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        return

    # Build join URL
    join_url = None
    if campaign.invite_url:
        join_url = campaign.invite_url
    elif campaign.telegram_username:
        join_url = f"https://t.me/{campaign.telegram_username.lstrip('@')}"

    text = _build_task_text(campaign)
    if count > 1:
        text += f"\n\n📋 {count - 1} more task(s) available after this."

    keyboard = (
        task_keyboard(campaign.id, join_url)
        if join_url
        else task_no_join_keyboard(campaign.id)
    )

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def handle_task_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed DONE — verify membership and award reward."""
    query = update.callback_query
    await query.answer("⏳ Verifying...")

    user = update.effective_user
    campaign_id = int(query.data.split(":")[1])

    # Rate limit
    if not await RateLimitMiddleware.check_task_verify(user.id):
        await query.answer("⏳ Too many attempts. Wait 30 seconds.", show_alert=True)
        return

    # Verify membership
    async with get_session() as session:
        verification = await VerificationService.verify_task_completion(
            bot=context.bot,
            session=session,
            user_id=user.id,
            campaign_id=campaign_id,
        )

    if not verification.success:
        reason = verification.reason
        if reason == FailureReason.NOT_MEMBER:
            msg = (
                "❌ <b>Verification Failed</b>\n\n"
                "You are not a member of the required channel/group.\n"
                "Please join first, then press DONE again."
            )
        elif reason == FailureReason.ALREADY_COMPLETED:
            msg = "✅ You've already completed this task!"
        elif reason == FailureReason.CAMPAIGN_EXPIRED:
            msg = "⏰ This task has expired."
        elif reason == FailureReason.CAMPAIGN_BUDGET_EXHAUSTED:
            msg = "💸 This task's budget is exhausted."
        elif reason in (FailureReason.USER_BANNED, FailureReason.USER_RESTRICTED):
            msg = "🚫 Your account is restricted from completing tasks."
        else:
            msg = f"❌ Verification failed: {verification.error_message}"

        # Record failed verify for analytics
        if reason == FailureReason.NOT_MEMBER:
            async with get_session() as session:
                async with session.begin():
                    await TaskService.record_failed_verify(session, campaign_id)

        await query.edit_message_text(msg, parse_mode="HTML")
        return

    # Execute reward atomically
    try:
        async with get_session() as session:
            async with session.begin():
                completion = await RewardService.execute_reward(
                    session=session,
                    user_id=user.id,
                    campaign_id=campaign_id,
                    verification_result=verification,
                )

                # Get updated balance
                from models.user import User
                db_user = await session.get(User, user.id)
                new_balance = db_user.balance
                reward_amount = completion.reward_amount

                # Pay referral commission (non-blocking)
                asyncio.create_task(
                    RewardService.pay_referral_commission(
                        session=session,
                        referred_user_id=user.id,
                        campaign_id=campaign_id,
                        task_reward_amount=reward_amount,
                    )
                )

        # Notify user
        asyncio.create_task(
            NotificationService.task_reward_earned(user.id, reward_amount, new_balance)
        )

        await query.edit_message_text(
            f"✅ <b>Task Completed!</b>\n\n"
            f"🎁 You earned: <b>{fmt_usdt(reward_amount)} USDT</b>\n"
            f"💰 New Balance: <b>{fmt_usdt(new_balance)} USDT</b>\n\n"
            f"Use /tasks to find more tasks!",
            parse_mode="HTML",
        )

    except Exception as e:
        log.error("Reward execution failed", user_id=user.id, campaign_id=campaign_id, error=str(e))
        await query.edit_message_text(
            "❌ An error occurred while processing your reward. Please try again.",
            parse_mode="HTML",
        )


async def handle_task_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed SKIP — record skip and show next task."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    campaign_id = int(query.data.split(":")[1])

    async with get_session() as session:
        async with session.begin():
            await TaskService.record_skip(session, user.id, campaign_id)

    await query.edit_message_text("⏭ Task skipped. Use the button below for the next task.")
    await handle_tasks(update, context)


async def handle_task_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show next task."""
    await handle_tasks(update, context)
