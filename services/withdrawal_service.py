"""
Withdrawal Service — full withdrawal lifecycle management.
PENDING → PROCESSING → PAID | FAILED
Failed payouts MUST atomically refund user balance.
"""
import hashlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user import User, UserStatus
from models.withdrawal import Withdrawal, WithdrawalStatus
from models.transaction import TransactionType
from services.ledger_service import LedgerService, InsufficientFundsError
from utils.wallet_utils import validate_bsc_address

log = structlog.get_logger(__name__)


def _make_withdrawal_idempotency_key(withdrawal_id: int) -> str:
    raw = f"withdrawal:{withdrawal_id}:{settings.SECRET_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _make_withdrawal_refund_key(withdrawal_id: int) -> str:
    raw = f"withdrawal_refund:{withdrawal_id}:{settings.SECRET_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


class WithdrawalValidationError(Exception):
    pass


class WithdrawalService:

    @staticmethod
    async def validate_withdrawal_request(
        session: AsyncSession,
        user_id: int,
        amount: Decimal,
        destination_wallet: str,
    ) -> None:
        """
        Validate all pre-conditions before creating a withdrawal.
        Raises WithdrawalValidationError with a user-facing message on any failure.
        """
        # Wallet format
        if not validate_bsc_address(destination_wallet):
            raise WithdrawalValidationError(
                "❌ Invalid BSC wallet address. Please provide a valid checksum address."
            )

        # Amount limits
        if amount < settings.MIN_WITHDRAWAL:
            raise WithdrawalValidationError(
                f"❌ Minimum withdrawal is {settings.MIN_WITHDRAWAL} USDT"
            )
        if amount > settings.MAX_WITHDRAWAL:
            raise WithdrawalValidationError(
                f"❌ Maximum withdrawal is {settings.MAX_WITHDRAWAL} USDT"
            )

        # Load user
        user = await session.get(User, user_id)
        if not user:
            raise WithdrawalValidationError("❌ User not found")

        # Status check
        if user.status == UserStatus.BANNED:
            raise WithdrawalValidationError("❌ Your account is banned")
        if user.status == UserStatus.RESTRICTED:
            raise WithdrawalValidationError(
                "❌ Withdrawals are temporarily restricted on your account. Contact support."
            )

        # Fraud score check
        if user.fraud_score >= settings.FRAUD_RESTRICT_SCORE:
            raise WithdrawalValidationError(
                "❌ Withdrawal restricted due to account review. Contact support."
            )

        # Balance check
        if user.balance < amount:
            raise WithdrawalValidationError(
                f"❌ Insufficient balance. Available: {user.balance:.8f} USDT"
            )

        # Account age check (24h minimum)
        min_age = timedelta(hours=24)
        if datetime.now(tz=timezone.utc) - user.joined_at < min_age:
            raise WithdrawalValidationError(
                "❌ Withdrawals are available 24 hours after registration"
            )

        # No pending/processing withdrawal
        existing = await session.execute(
            select(Withdrawal).where(
                Withdrawal.user_id == user_id,
                Withdrawal.status.in_([
                    WithdrawalStatus.PENDING,
                    WithdrawalStatus.PROCESSING,
                ])
            )
        )
        if existing.scalar_one_or_none():
            raise WithdrawalValidationError(
                "❌ You already have a pending withdrawal. Please wait for it to complete."
            )

    @staticmethod
    async def create_withdrawal(
        session: AsyncSession,
        user_id: int,
        amount: Decimal,
        destination_wallet: str,
    ) -> Withdrawal:
        """
        Create withdrawal record and debit user balance atomically.
        Must be called within session.begin().
        """
        import uuid
        idempotency_key = hashlib.sha256(
            f"wd_create:{user_id}:{amount}:{uuid.uuid4()}:{settings.SECRET_SALT}".encode()
        ).hexdigest()

        # Debit user balance
        await LedgerService.debit_user(
            session=session,
            user_id=user_id,
            amount=amount,
            tx_type=TransactionType.WITHDRAWAL,
            reference_type="withdrawal",
            idempotency_key=idempotency_key,
            description=f"Withdrawal request: {amount} USDT to {destination_wallet[-8:]}",
        )

        withdrawal = Withdrawal(
            user_id=user_id,
            amount=amount,
            network="BSC",
            destination_wallet=destination_wallet,
            status=WithdrawalStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        session.add(withdrawal)
        await session.flush()

        log.info(
            "Withdrawal created",
            user_id=user_id,
            amount=str(amount),
            withdrawal_id=withdrawal.id,
        )
        return withdrawal

    @staticmethod
    async def process_withdrawal(
        session: AsyncSession,
        withdrawal_id: int,
    ) -> bool:
        """
        Execute an on-chain payout for a PENDING withdrawal.
        Returns True on success, False on failure (balance already refunded on failure).
        Must be called within session.begin().
        """
        from services.blockchain_service import get_blockchain_service

        # Lock withdrawal row
        result = await session.execute(
            select(Withdrawal)
            .where(Withdrawal.id == withdrawal_id)
            .with_for_update(nowait=True)
        )
        withdrawal = result.scalar_one_or_none()

        if not withdrawal:
            log.error("Withdrawal not found", withdrawal_id=withdrawal_id)
            return False

        if withdrawal.status != WithdrawalStatus.PENDING:
            log.warning(
                "Withdrawal not in PENDING state",
                withdrawal_id=withdrawal_id,
                status=withdrawal.status,
            )
            return False

        # Mark as processing
        withdrawal.status = WithdrawalStatus.PROCESSING
        await session.flush()

        blockchain = get_blockchain_service()
        result = await blockchain.send_usdt(
            to_address=withdrawal.destination_wallet,
            amount=withdrawal.amount,
            private_key=settings.PAYOUT_PRIVATE_KEY,
            idempotency_key=withdrawal.idempotency_key,
        )

        if result["success"]:
            withdrawal.status = WithdrawalStatus.PAID
            withdrawal.tx_hash = result["tx_hash"]
            withdrawal.block_number = result.get("block_number")
            withdrawal.gas_used = result.get("gas_used")
            withdrawal.processed_at = datetime.now(tz=timezone.utc)
            await session.flush()

            log.info(
                "Withdrawal paid",
                withdrawal_id=withdrawal_id,
                tx_hash=result["tx_hash"],
                amount=str(withdrawal.amount),
            )
            return True
        else:
            # CRITICAL: Refund user balance on failure
            await WithdrawalService._refund_failed_withdrawal(session, withdrawal, result["error"])
            return False

    @staticmethod
    async def _refund_failed_withdrawal(
        session: AsyncSession,
        withdrawal: Withdrawal,
        failure_reason: str,
    ) -> None:
        """
        Atomically refund user after a failed payout.
        This MUST succeed — if it fails, escalate to admin immediately.
        """
        refund_key = _make_withdrawal_refund_key(withdrawal.id)

        try:
            await LedgerService.credit_user(
                session=session,
                user_id=withdrawal.user_id,
                amount=withdrawal.amount,
                tx_type=TransactionType.WITHDRAWAL_RETURN,
                reference_id=withdrawal.id,
                reference_type="withdrawal",
                idempotency_key=refund_key,
                description=f"Refund: failed withdrawal #{withdrawal.id}",
                update_total_earned=False,
            )
            withdrawal.status = WithdrawalStatus.FAILED
            withdrawal.failure_reason = failure_reason[:500]
            withdrawal.processed_at = datetime.now(tz=timezone.utc)
            await session.flush()

            log.info(
                "Failed withdrawal refunded",
                withdrawal_id=withdrawal.id,
                amount=str(withdrawal.amount),
                user_id=withdrawal.user_id,
            )
        except Exception as e:
            log.critical(
                "CRITICAL: Failed to refund withdrawal — manual intervention required",
                withdrawal_id=withdrawal.id,
                user_id=withdrawal.user_id,
                amount=str(withdrawal.amount),
                error=str(e),
            )
            raise  # Propagate — this is a critical error
