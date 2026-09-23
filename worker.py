"""
Worker — APScheduler background jobs runner.
Each job uses a Redis distributed lock to prevent parallel execution.
"""
import asyncio
import contextlib
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from database import init_db, close_db, get_session, get_redis

log = structlog.get_logger(__name__)


@contextlib.asynccontextmanager
async def redis_lock(name: str, timeout: int = 300):
    """Distributed Redis lock. Yields True if lock acquired, False otherwise."""
    redis = get_redis()
    lock_key = f"job_lock:{name}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=timeout)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            await redis.delete(lock_key)


async def job_expire_campaigns():
    """Every 5 min — expire overdue campaigns, release budgets."""
    async with redis_lock("expire_campaigns", timeout=240):
        try:
            async with get_session() as session:
                async with session.begin():
                    from services.campaign_service import CampaignService
                    count = await CampaignService.expire_overdue_campaigns(session)
            if count:
                log.info("Campaigns expired", count=count)
        except Exception as e:
            log.error("job_expire_campaigns failed", error=str(e))


async def job_process_withdrawals():
    """Every 2 min — process PENDING withdrawals."""
    if not settings.AUTO_PAYOUT_ENABLED:
        return

    async with redis_lock("process_withdrawals", timeout=110):
        try:
            async with get_session() as session:
                from sqlalchemy import select
                from models.withdrawal import Withdrawal, WithdrawalStatus

                result = await session.execute(
                    select(Withdrawal)
                    .where(Withdrawal.status == WithdrawalStatus.PENDING)
                    .order_by(Withdrawal.created_at.asc())
                    .limit(10)
                )
                pending = result.scalars().all()
                withdrawal_ids = [w.id for w in pending]

            for wd_id in withdrawal_ids:
                try:
                    async with get_session() as session:
                        async with session.begin():
                            from services.withdrawal_service import WithdrawalService
                            success = await WithdrawalService.process_withdrawal(session, wd_id)

                    # Notify user
                    async with get_session() as session:
                        from models.withdrawal import Withdrawal
                        wd = await session.get(Withdrawal, wd_id)
                        if wd:
                            from services.notification_service import NotificationService
                            if wd.status.value == "PAID":
                                await NotificationService.withdrawal_paid(
                                    wd.user_id, wd.amount, wd.tx_hash or ""
                                )
                            elif wd.status.value == "FAILED":
                                await NotificationService.withdrawal_failed(
                                    wd.user_id, wd.amount
                                )
                except Exception as e:
                    log.error("Withdrawal processing error", withdrawal_id=wd_id, error=str(e))

        except Exception as e:
            log.error("job_process_withdrawals failed", error=str(e))


async def job_monitor_deposits():
    """Every 3 min — check pending BSC deposits for confirmations."""
    async with redis_lock("monitor_deposits", timeout=150):
        try:
            async with get_session() as session:
                async with session.begin():
                    from services.deposit_service import DepositService
                    count = await DepositService.check_pending_deposits(session)
            if count:
                log.info("Deposits confirmed", count=count)
        except Exception as e:
            log.error("job_monitor_deposits failed", error=str(e))


async def job_retry_failed_payouts():
    """Every 15 min — retry FAILED withdrawals (max 3 attempts)."""
    async with redis_lock("retry_failed_payouts", timeout=840):
        try:
            async with get_session() as session:
                from sqlalchemy import select
                from models.withdrawal import Withdrawal, WithdrawalStatus

                result = await session.execute(
                    select(Withdrawal).where(
                        Withdrawal.status == WithdrawalStatus.FAILED,
                        Withdrawal.retry_count < 3,
                    ).limit(5)
                )
                failed = result.scalars().all()
                ids = [w.id for w in failed]

            for wd_id in ids:
                try:
                    async with get_session() as session:
                        async with session.begin():
                            # Reset to PENDING for reprocessing
                            from models.withdrawal import Withdrawal
                            wd = await session.get(Withdrawal, wd_id)
                            if wd and wd.retry_count < 3:
                                from models.transaction import TransactionType
                                from services.ledger_service import LedgerService
                                import hashlib

                                # Re-debit user (refund was applied on failure)
                                redebit_key = hashlib.sha256(
                                    f"wd_retry_debit:{wd_id}:{wd.retry_count}:{settings.SECRET_SALT}".encode()
                                ).hexdigest()
                                await LedgerService.debit_user(
                                    session=session,
                                    user_id=wd.user_id,
                                    amount=wd.amount,
                                    tx_type=TransactionType.WITHDRAWAL,
                                    idempotency_key=redebit_key,
                                    description=f"Retry withdrawal #{wd_id}",
                                )
                                wd.status = WithdrawalStatus.PENDING
                                wd.retry_count += 1
                                wd.failure_reason = None

                    log.info("Withdrawal queued for retry", withdrawal_id=wd_id)
                except Exception as e:
                    log.error("Retry setup failed", withdrawal_id=wd_id, error=str(e))

        except Exception as e:
            log.error("job_retry_failed_payouts failed", error=str(e))


async def job_fraud_monitor():
    """Every 10 min — recalculate fraud scores for flagged users."""
    async with redis_lock("fraud_monitor", timeout=580):
        try:
            async with get_session() as session:
                from sqlalchemy import select
                from models.user import User, UserStatus

                result = await session.execute(
                    select(User.id).where(
                        User.status.in_([UserStatus.FLAGGED, UserStatus.RESTRICTED])
                    ).limit(100)
                )
                user_ids = [row[0] for row in result.all()]

            for uid in user_ids:
                try:
                    async with get_session() as session:
                        async with session.begin():
                            from services.fraud_service import FraudService
                            await FraudService.recalculate_fraud_score(session, uid)
                except Exception as e:
                    log.error("Fraud score recalc failed", user_id=uid, error=str(e))

        except Exception as e:
            log.error("job_fraud_monitor failed", error=str(e))


async def job_cleanup():
    """Daily — clean up stale Redis keys."""
    async with redis_lock("cleanup", timeout=3600):
        try:
            redis = get_redis()
            # Clean up old rate limit keys (they have TTL but let's be explicit)
            keys = await redis.keys("rate:*")
            pipe = redis.pipeline()
            for key in keys:
                ttl = await redis.ttl(key)
                if ttl < 0:
                    pipe.delete(key)
            await pipe.execute()
            log.info("Cleanup complete", keys_checked=len(keys))
        except Exception as e:
            log.error("job_cleanup failed", error=str(e))


async def check_hot_wallet_balance():
    """Every 30 min — alert admin if hot wallet balance is low."""
    try:
        from services.blockchain_service import get_blockchain_service
        blockchain = get_blockchain_service()
        usdt_bal = await blockchain.get_usdt_balance(settings.PAYOUT_WALLET_ADDRESS)
        bnb_bal = await blockchain.get_bnb_balance(settings.PAYOUT_WALLET_ADDRESS)

        if bnb_bal < 0.01:
            from services.notification_service import NotificationService
            await NotificationService.notify_admin_critical(
                f"🔴 Hot wallet BNB LOW: {bnb_bal:.4f} BNB\n"
                f"Gas transactions may fail!"
            )
        if usdt_bal < 10:
            from services.notification_service import NotificationService
            await NotificationService.notify_admin_critical(
                f"🔴 Hot wallet USDT LOW: {usdt_bal:.4f} USDT\n"
                f"Payouts may fail!"
            )
    except Exception as e:
        log.error("Wallet balance check failed", error=str(e))


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(job_expire_campaigns, IntervalTrigger(minutes=5), id="expire_campaigns")
    scheduler.add_job(job_process_withdrawals, IntervalTrigger(minutes=2), id="process_withdrawals")
    scheduler.add_job(job_monitor_deposits, IntervalTrigger(minutes=3), id="monitor_deposits")
    scheduler.add_job(job_retry_failed_payouts, IntervalTrigger(minutes=15), id="retry_payouts")
    scheduler.add_job(job_fraud_monitor, IntervalTrigger(minutes=10), id="fraud_monitor")
    scheduler.add_job(job_cleanup, IntervalTrigger(hours=24), id="cleanup")
    scheduler.add_job(check_hot_wallet_balance, IntervalTrigger(minutes=30), id="wallet_balance")

    return scheduler


async def main():
    """Worker entry point."""
    import logging as stdlib_logging
    import structlog

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    stdlib_logging.basicConfig(level=getattr(stdlib_logging, settings.LOG_LEVEL.upper()))

    log.info("Worker starting")
    await init_db()

    # Set up notification bot
    from telegram import Bot
    from services.notification_service import set_bot
    bot = Bot(token=settings.BOT_TOKEN)
    set_bot(bot)

    scheduler = build_scheduler()
    scheduler.start()
    log.info("Scheduler started", jobs=len(scheduler.get_jobs()))

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker shutting down")
        scheduler.shutdown()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
