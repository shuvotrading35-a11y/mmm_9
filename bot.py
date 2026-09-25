"""
GLOBAL TASK EARN — Main Bot Entry Point
"""
import asyncio
import signal
import structlog
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
    ContextTypes,
    ChatMemberHandler,
    TypeHandler,
    ApplicationHandlerStop,
)

from config import settings
from database import init_db, close_db

from handlers.start import cmd_start, cmd_help, handle_main_menu, handle_user_cancel
from handlers.profile import handle_profile, profile_conv_handler
from handlers.tasks import (
    handle_tasks, handle_task_done, handle_task_skip, handle_task_next
)
from handlers.withdraw import withdraw_conv_handler
from handlers.referral import handle_referral
from handlers.statistics import handle_statistics
from handlers.live_payments import handle_live_payments
from handlers.promotion import handle_promotion
from handlers.support import support_conv_handler
from handlers.force_join import handle_force_join_check
from handlers.chat_member import on_chat_member_update

from admin.panel import (
    admin_panel_handler, admin_callback_handler,
    admin_panel_reply_handler,
    admin_users_reply, admin_campaigns_reply, admin_sponsors_reply,
    admin_deposits_reply, admin_withdrawals_reply, admin_referrals_reply,
    admin_stats_reply, admin_broadcast_reply, admin_banned_reply,
    admin_settings_reply, admin_fraud_reply, admin_audit_reply,
    admin_back_reply, admin_close_reply, admin_cancel_reply,
    admin_text_input_dispatcher,
    admin_force_join_reply,
)
from sponsor.panel import (
    sponsor_panel_handler, sponsor_callback_handler,
    sponsor_panel_reply_handler, sponsor_create_campaign_reply,
    sponsor_my_campaigns_reply, sponsor_deposit_reply,
    sponsor_analytics_reply, sponsor_wallet_reply,
    sponsor_support_reply, sponsor_back_reply,
    sponsor_task_type_reply, sponsor_duration_reply,
    sponsor_cancel_reply,
    sponsor_text_input_handler,
)

log = structlog.get_logger(__name__)


async def post_init(application: Application) -> None:
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Get help"),
        BotCommand("profile", "View your profile"),
        BotCommand("tasks", "Browse available tasks"),
        BotCommand("withdraw", "Withdraw earnings"),
        BotCommand("referral", "Referral info"),
        BotCommand("stats", "Platform statistics"),
    ]
    await application.bot.set_my_commands(commands)
    log.info("Bot commands set")

    try:
        from services.notification_service import NotificationService
        for name in ("set_bot", "set_application", "configure", "init"):
            m = getattr(NotificationService, name, None)
            if callable(m):
                try:
                    m(application.bot)
                except TypeError:
                    m(bot=application.bot)
                log.info("NotificationService initialized", method=name)
                break
    except Exception:
        log.exception("NotificationService setup skipped")

    # ── Schedule periodic force-join membership check ──
    try:
        async def _force_join_periodic_job():
            try:
                from services.force_join_service import ForceJoinService
                await ForceJoinService.run_periodic_check(application.bot)
            except Exception:
                log.exception("Force-join periodic job failed")

        application.job_queue.run_repeating(
            _force_join_periodic_job,
            interval=6 * 3600,
            first=300,
            name="force_join_periodic_check",
            job_kwargs={"misfire_grace_time": 300, "coalesce": True},
        )
        log.info("Force-join periodic check scheduled (every 6h)")
    except Exception:
        log.exception("Failed to schedule force-join periodic check")


async def post_shutdown(application: Application) -> None:
    await close_db()
    log.info("Database connections closed")


async def _global_force_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global gate — runs BEFORE every other handler (group -20).

    Any update from a user who hasn't joined all required channels is blocked
    here, and the join prompt is sent. Raises ApplicationHandlerStop so no
    other handler runs for that update.

    Admins bypass. /start, /help, the verify button, and Cancel buttons are
    allowed through so the user can actually join.
    """
    if not settings.FORCE_JOIN_ENABLED:
        return

    user = update.effective_user
    if not user:
        return

    # Admins bypass
    if user.id in settings.ADMIN_IDS:
        return

    # Allow-through list (so user can join / abort)
    if update.message and update.message.text:
        t = update.message.text.strip()
        if (
            t.startswith("/start")
            or t.startswith("/help")
            or t in ("🏠 Main Menu", "❌ Cancel", "❌ Cancel Sponsor", "❌ Cancel Admin")
        ):
            return

    if update.callback_query:
        data = update.callback_query.data or ""
        if data == "force_join_check":
            return

    # Everything else: check membership
    try:
        from middlewares.force_join_middleware import ForceJoinMiddleware
        passed = await ForceJoinMiddleware.check(update, context)
        if not passed:
            raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception:
        # Don't block bot on unexpected errors
        log.exception("Force-join gate error")


def build_application() -> Application:
    builder = ApplicationBuilder()
    builder.token(settings.BOT_TOKEN)
    builder.post_init(post_init)
    builder.post_shutdown(post_shutdown)
    builder.concurrent_updates(True)

    if settings.WEBHOOK_URL:
        builder.updater(None)

    app = builder.build()

    # ══════════════════════════════════════════════════════════
    # Chat member leave detection
    # ══════════════════════════════════════════════════════════
    app.add_handler(ChatMemberHandler(
        on_chat_member_update,
        ChatMemberHandler.CHAT_MEMBER,
    ))

    # ══════════════════════════════════════════════════════════
    # -20. GLOBAL FORCE JOIN GATE — runs before everything
    # ══════════════════════════════════════════════════════════
    app.add_handler(TypeHandler(Update, _global_force_join_gate), group=-20)

    # ══════════════════════════════════════════════════════════
    # GROUP 0 — all handler registrations
    # ══════════════════════════════════════════════════════════

    # 1. Conversation handlers
    app.add_handler(profile_conv_handler())
    app.add_handler(withdraw_conv_handler())
    app.add_handler(support_conv_handler())

    # 2. Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", handle_profile))
    app.add_handler(CommandHandler("tasks", handle_tasks))
    app.add_handler(CommandHandler("withdraw", handle_withdraw_cmd))
    app.add_handler(CommandHandler("referral", handle_referral))
    app.add_handler(CommandHandler("stats", handle_statistics))
    app.add_handler(CommandHandler("admin", admin_panel_handler))
    app.add_handler(CommandHandler("sponsor", sponsor_panel_handler))

    # 3. SPONSOR reply keyboard
    app.add_handler(MessageHandler(filters.Regex(r"Sponsor Panel$"), sponsor_panel_reply_handler))
    app.add_handler(MessageHandler(filters.Regex(r"Create Campaign$"), sponsor_create_campaign_reply))
    app.add_handler(MessageHandler(filters.Regex(r"My Campaigns$"), sponsor_my_campaigns_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Deposit USDT$"), sponsor_deposit_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Analytics$"), sponsor_analytics_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Wallet Info$"), sponsor_wallet_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Sponsor Support$"), sponsor_support_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Back to Sponsor Panel$"), sponsor_back_reply))
    app.add_handler(MessageHandler(
        filters.Regex(r"Channel Join$|Group Join$|Bot Start$|Channel \+ Group$"),
        sponsor_task_type_reply
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^1 Day$|^3 Days$|^7 Days$|^30 Days$"),
        sponsor_duration_reply
    ))
    app.add_handler(MessageHandler(filters.Regex(r"Cancel Sponsor$"), sponsor_cancel_reply))

    # 4. ADMIN reply keyboard
    app.add_handler(MessageHandler(filters.Regex(r"Users$"), admin_users_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Campaigns$"), admin_campaigns_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Sponsors$"), admin_sponsors_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Deposits$"), admin_deposits_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Withdrawals$"), admin_withdrawals_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Referrals$"), admin_referrals_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Admin Stats$"), admin_stats_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Broadcast$"), admin_broadcast_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Force Join$"), admin_force_join_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Banned Users$"), admin_banned_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Settings$"), admin_settings_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Fraud Monitor$"), admin_fraud_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Audit Logs$"), admin_audit_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Back to Admin Panel$"), admin_back_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Close Admin Panel$"), admin_close_reply))
    app.add_handler(MessageHandler(filters.Regex(r"Cancel Admin$"), admin_cancel_reply))

    # 5. Main menu reply buttons
    app.add_handler(MessageHandler(filters.Regex(r"Profile$"), handle_profile))
    app.add_handler(MessageHandler(filters.Regex(r"Live Payments$"), handle_live_payments))
    app.add_handler(MessageHandler(filters.Regex(r"View Tasks$"), handle_tasks))
    app.add_handler(MessageHandler(filters.Regex(r"Referral$"), handle_referral))
    app.add_handler(MessageHandler(filters.Regex(r"Withdraw$"), handle_withdraw_menu))
    app.add_handler(MessageHandler(filters.Regex(r"Stats$"), handle_statistics))
    app.add_handler(MessageHandler(filters.Regex(r"Promotion$"), handle_promotion))
    app.add_handler(MessageHandler(filters.Regex(r"Support$"), handle_support_menu))

    # 6. Navigation
    app.add_handler(MessageHandler(filters.Regex(r"Main Menu$"), handle_main_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^Cancel$"), handle_user_cancel))

    # ══════════════════════════════════════════════════════════
    # 7. COMBINED free-text dispatcher — last in group 0
    # ══════════════════════════════════════════════════════════
    async def _combined_text_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        text = update.message.text

        if text.lower() in ("/cancel", "cancel"):
            has_state = any(
                context.user_data.get(k) for k in (
                    "admin_awaiting_sponsor_balance",
                    "admin_awaiting_user_balance",
                    "admin_awaiting_user_search",
                    "admin_awaiting_broadcast",
                    "admin_awaiting_fj_add",
                    "sponsor_step",
                )
            )
            if has_state:
                context.user_data.clear()
                await update.message.reply_text("❌ Cancelled.")
                return

        if settings.is_admin(update.effective_user.id):
            if any([
                context.user_data.get("admin_awaiting_sponsor_balance"),
                context.user_data.get("admin_awaiting_user_balance"),
                context.user_data.get("admin_awaiting_user_search"),
                context.user_data.get("admin_awaiting_broadcast"),
                context.user_data.get("admin_awaiting_fj_add"),
            ]):
                await admin_text_input_dispatcher(update, context)
                return

        if context.user_data.get("sponsor_step"):
            await sponsor_text_input_handler(update, context)
            return

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        _combined_text_dispatcher,
    ))

    # ══════════════════════════════════════════════════════════
    # Callback handlers
    # ══════════════════════════════════════════════════════════
    app.add_handler(CallbackQueryHandler(handle_force_join_check, pattern=r"^force_join_check$"))
    app.add_handler(CallbackQueryHandler(handle_task_done, pattern=r"^task_done:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_task_skip, pattern=r"^task_skip:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_task_next, pattern=r"^task_next$"))
    app.add_handler(CallbackQueryHandler(handle_live_payments, pattern=r"^live_refresh$"))
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(sponsor_callback_handler, pattern=r"^sponsor:"))

    app.add_error_handler(error_handler)
    return app


async def handle_withdraw_cmd(update, context):
    from handlers.withdraw import withdraw_start
    await withdraw_start(update, context)


async def handle_withdraw_menu(update, context):
    from handlers.withdraw import withdraw_start
    await withdraw_start(update, context)


async def handle_support_menu(update, context):
    from handlers.support import support_start
    await support_start(update, context)


async def error_handler(update, context):
    log.error("Unhandled exception", error=str(context.error), exc_info=context.error)
    if settings.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=settings.ADMIN_IDS[0],
                text=f"⚠️ <code>{str(context.error)[:500]}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def run_polling(app: Application) -> None:
    log.info("Starting in polling mode")
    try:
        log.info("Connecting to database and Redis...")
        await init_db()
        log.info("Database initialized")
    except Exception:
        log.exception("init_db failed")
        raise

    async with app:
        await app.start()
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        log.info("Bot polling started")

        stop = asyncio.Event()
        loop = asyncio.get_event_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(s, stop.set)
        await stop.wait()

        await app.updater.stop()
        await app.stop()


async def run_webhook(app: Application) -> None:
    log.info("Starting in webhook mode", url=settings.WEBHOOK_URL)
    await init_db()
    log.info("Database initialized")

    await app.initialize()
    await app.start()
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=settings.WEBHOOK_PORT,
        url_path=settings.BOT_TOKEN,
        webhook_url=f"{settings.WEBHOOK_URL}/{settings.BOT_TOKEN}",
        secret_token=settings.WEBHOOK_SECRET or None,
        allowed_updates=Update.ALL_TYPES,
    )
    log.info("Webhook started")

    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, stop.set)
    await stop.wait()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


def main() -> None:
    import logging as stdlib_logging

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
            if settings.LOG_FORMAT == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    stdlib_logging.basicConfig(
        level=getattr(stdlib_logging, settings.LOG_LEVEL.upper(), stdlib_logging.INFO)
    )

    app = build_application()
    if settings.WEBHOOK_URL:
        asyncio.run(run_webhook(app))
    else:
        asyncio.run(run_polling(app))


if __name__ == "__main__":
    main()