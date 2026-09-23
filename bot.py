"""
GLOBAL TASK EARN — Main Bot Entry Point
Supports both webhook and polling mode via environment config.
"""
import asyncio
import logging
import signal
import structlog
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
    ConversationHandler
)

from config import settings
from database import init_db, close_db
from middlewares.auth_middleware import AuthMiddleware
from middlewares.ban_middleware import BanMiddleware
from middlewares.force_join_middleware import ForceJoinMiddleware
from middlewares.rate_limit_middleware import RateLimitMiddleware
from middlewares.maintenance_middleware import MaintenanceMiddleware
from middlewares.logging_middleware import LoggingMiddleware

from handlers.start import (
    cmd_start, cmd_help,
    STATES as START_STATES
)
from handlers.profile import (
    handle_profile, handle_set_wallet,
    WALLET_INPUT, profile_conv_handler
)
from handlers.tasks import (
    handle_tasks, handle_task_done, handle_task_skip,
    handle_task_next
)
from handlers.withdraw import withdraw_conv_handler
from handlers.referral import handle_referral
from handlers.statistics import handle_statistics
from handlers.live_payments import handle_live_payments
from handlers.promotion import handle_promotion
from handlers.support import support_conv_handler
from handlers.force_join import handle_force_join_check

from admin.panel import (
    admin_panel_handler, admin_callback_handler
)
from sponsor.panel import (
    sponsor_panel_handler, sponsor_callback_handler
)

log = structlog.get_logger(__name__)


async def post_init(application: Application) -> None:
    """Set bot commands after bot starts. DB is already initialized in run_*()."""
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

    # ── NotificationService-এ bot সেট করা (init হওয়ার পর) ──
    try:
        from services.notification_service import NotificationService
        # সম্ভাব্য সব মেথড নাম চেক করা
        for method_name in ("set_bot", "set_application", "configure", "init"):
            method = getattr(NotificationService, method_name, None)
            if callable(method):
                try:
                    method(application.bot)
                except TypeError:
                    method(bot=application.bot)
                log.info("NotificationService initialized", method=method_name)
                break
        else:
            log.warning("NotificationService has no known setter method")
    except ImportError:
        log.warning("NotificationService module not found — skipping")
    except Exception:
        log.exception("NotificationService setup failed")


async def post_shutdown(application: Application) -> None:
    """Cleanup on shutdown."""
    await close_db()
    log.info("Database connections closed")


def build_application() -> Application:
    """Build and configure the Telegram application."""
    builder = ApplicationBuilder()
    builder.token(settings.BOT_TOKEN)
    builder.post_init(post_init)
    builder.post_shutdown(post_shutdown)
    builder.concurrent_updates(True)

    if settings.WEBHOOK_URL:
        builder.updater(None)  # Disable updater for webhook mode

    app = builder.build()

    # Register middleware (PTB uses custom update processors)
    # Order matters: maintenance → ban → force_join → rate_limit → auth → logging
    app.add_handler(MessageHandler(
        filters.ALL,
        MaintenanceMiddleware.process,
    ), group=-10)
    app.add_handler(CallbackQueryHandler(
        MaintenanceMiddleware.process_callback
    ), group=-10)

    # Conversation handlers (must be registered before generic handlers)
    app.add_handler(profile_conv_handler())
    app.add_handler(withdraw_conv_handler())
    app.add_handler(support_conv_handler())

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", handle_profile))
    app.add_handler(CommandHandler("tasks", handle_tasks))
    app.add_handler(CommandHandler("withdraw", handle_withdraw_cmd))
    app.add_handler(CommandHandler("referral", handle_referral))
    app.add_handler(CommandHandler("stats", handle_statistics))
    app.add_handler(CommandHandler("admin", admin_panel_handler))

    # Message handlers (ReplyKeyboard button text)
    app.add_handler(MessageHandler(
        filters.Regex(r"^👤 Profile$"), handle_profile
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^💰 Live Payments$"), handle_live_payments
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^📋 View Tasks$"), handle_tasks
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^🎁 Referral$"), handle_referral
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^💳 Withdraw$"), handle_withdraw_menu
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^📊 Statistics$"), handle_statistics
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^📣 Promotion$"), handle_promotion
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^🆘 Support$"), handle_support_menu
    ))
    app.add_handler(MessageHandler(
        filters.Regex(r"^💼 Sponsor Panel$"), sponsor_panel_handler
    ))

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(
        handle_task_done, pattern=r"^task_done:\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        handle_task_skip, pattern=r"^task_skip:\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        handle_task_next, pattern=r"^task_next$"
    ))
    app.add_handler(CallbackQueryHandler(
        handle_live_payments, pattern=r"^live_refresh$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_callback_handler, pattern=r"^admin:"
    ))
    app.add_handler(CallbackQueryHandler(
        sponsor_callback_handler, pattern=r"^sponsor:"
    ))

    # Error handler
    app.add_error_handler(error_handler)

    return app


async def handle_withdraw_cmd(update: Update, context) -> None:
    """Redirect to withdraw conversation."""
    from handlers.withdraw import withdraw_start
    await withdraw_start(update, context)


async def handle_withdraw_menu(update: Update, context) -> None:
    """Handle withdraw from menu button."""
    from handlers.withdraw import withdraw_start
    await withdraw_start(update, context)


async def handle_support_menu(update: Update, context) -> None:
    """Handle support from menu button."""
    from handlers.support import support_start
    await support_start(update, context)


async def error_handler(update: object, context) -> None:
    """Global error handler — logs error, notifies admin."""
    log.error(
        "Unhandled exception",
        error=str(context.error),
        update=str(update)[:200] if update else None,
        exc_info=context.error
    )
    # Notify admin of critical errors
    if settings.ADMIN_IDS:
        try:
            error_msg = (
                f"⚠️ Bot Error\n"
                f"<code>{str(context.error)[:500]}</code>"
            )
            await context.bot.send_message(
                chat_id=settings.ADMIN_IDS[0],
                text=error_msg,
                parse_mode="HTML"
            )
        except Exception:
            pass  # Don't let notification failure cascade


async def run_webhook(app: Application) -> None:
    """Run bot in webhook mode."""
    log.info("Starting in webhook mode", url=settings.WEBHOOK_URL)

    # ── Database / Redis প্রস্তুত ──
    try:
        log.info("Connecting to database and Redis...")
        await init_db()
        log.info("Database initialized")
    except Exception:
        log.exception("init_db failed")
        raise

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

    # Keep alive
    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, _signal_handler)
    loop.add_signal_handler(signal.SIGTERM, _signal_handler)

    await stop_event.wait()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


async def run_polling(app: Application) -> None:
    """Run bot in polling mode."""
    log.info("Starting in polling mode")

    # ── Database / Redis প্রস্তুত ──
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

        stop_event = asyncio.Event()

        def _signal_handler():
            stop_event.set()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)

        await stop_event.wait()

        await app.updater.stop()
        await app.stop()


def main() -> None:
    """Main entry point."""
    import logging as stdlib_logging
    import structlog

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