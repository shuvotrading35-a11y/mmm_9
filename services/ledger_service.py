"""
Ledger Service — double-entry financial ledger.
Every balance mutation goes through here. No exceptions.

Rules:
- All operations inside a transaction with SERIALIZABLE isolation
- Row-level locking with SELECT FOR UPDATE NOWAIT
- Idempotency checked before every write
- balance_before / balance_after always recorded
"""
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from models.sponsor import Sponsor
from models.transaction import Transaction, TransactionType, EntityType

log = structlog.get_logger(__name__)


class InsufficientFundsError(Exception):
    pass


class IdempotencyConflictError(Exception):
    """Raised when the same idempotency_key was already processed."""
    pass


class LockConflictError(Exception):
    """Raised when a row lock cannot be acquired immediately."""
    pass


async def _check_idempotency(
    session: AsyncSession,
    idempotency_key: str,
) -> Optional[Transaction]:
    """Check if a transaction with this key already exists."""
    result = await session.execute(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


class LedgerService:

    @staticmethod
    async def credit_user(
        session: AsyncSession,
        user_id: int,
        amount: Decimal,
        tx_type: TransactionType,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None,
        idempotency_key: str = "",
        description: str = "",
        update_total_earned: bool = True,
    ) -> Transaction:
        """
        Atomically credit a user balance.
        Must be called within an active transaction (session.begin() context).
        """
        if amount <= Decimal("0"):
            raise ValueError(f"Credit amount must be positive, got {amount}")

        # Idempotency check
        existing = await _check_idempotency(session, idempotency_key)
        if existing:
            log.info("Idempotent credit skipped", key=idempotency_key, tx_id=existing.id)
            raise IdempotencyConflictError(f"Transaction {idempotency_key} already processed")

        # Lock user row
        try:
            result = await session.execute(
                select(User)
                .where(User.id == user_id)
                .with_for_update(nowait=True)
            )
        except Exception as e:
            raise LockConflictError(f"Cannot acquire lock on user {user_id}: {e}") from e

        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        balance_before = user.balance
        user.balance += amount
        balance_after = user.balance

        if update_total_earned:
            user.total_earned += amount

        tx = Transaction(
            entity_type=EntityType.USER,
            entity_id=user_id,
            tx_type=tx_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()

        log.info(
            "User credited",
            user_id=user_id,
            amount=str(amount),
            tx_type=tx_type,
            balance_after=str(balance_after),
        )
        return tx

    @staticmethod
    async def debit_user(
        session: AsyncSession,
        user_id: int,
        amount: Decimal,
        tx_type: TransactionType,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None,
        idempotency_key: str = "",
        description: str = "",
    ) -> Transaction:
        """
        Atomically debit a user balance.
        Raises InsufficientFundsError if balance < amount.
        """
        if amount <= Decimal("0"):
            raise ValueError(f"Debit amount must be positive, got {amount}")

        # Idempotency check
        existing = await _check_idempotency(session, idempotency_key)
        if existing:
            raise IdempotencyConflictError(f"Transaction {idempotency_key} already processed")

        # Lock user row
        try:
            result = await session.execute(
                select(User)
                .where(User.id == user_id)
                .with_for_update(nowait=True)
            )
        except Exception as e:
            raise LockConflictError(f"Cannot acquire lock on user {user_id}: {e}") from e

        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        if user.balance < amount:
            raise InsufficientFundsError(
                f"User {user_id} balance {user.balance} < required {amount}"
            )

        balance_before = user.balance
        user.balance -= amount
        balance_after = user.balance

        if tx_type == TransactionType.WITHDRAWAL:
            user.total_withdrawn += amount

        tx = Transaction(
            entity_type=EntityType.USER,
            entity_id=user_id,
            tx_type=tx_type,
            amount=-amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()

        log.info(
            "User debited",
            user_id=user_id,
            amount=str(amount),
            tx_type=tx_type,
            balance_after=str(balance_after),
        )
        return tx

    @staticmethod
    async def credit_sponsor(
        session: AsyncSession,
        sponsor_id: int,
        amount: Decimal,
        tx_type: TransactionType,
        idempotency_key: str,
        description: str = "",
    ) -> Transaction:
        """Atomically credit a sponsor's available balance."""
        existing = await _check_idempotency(session, idempotency_key)
        if existing:
            raise IdempotencyConflictError(f"Transaction {idempotency_key} already processed")

        try:
            result = await session.execute(
                select(Sponsor)
                .where(Sponsor.id == sponsor_id)
                .with_for_update(nowait=True)
            )
        except Exception as e:
            raise LockConflictError(f"Cannot acquire lock on sponsor {sponsor_id}: {e}") from e

        sponsor = result.scalar_one_or_none()
        if not sponsor:
            raise ValueError(f"Sponsor {sponsor_id} not found")

        balance_before = sponsor.available_balance
        sponsor.available_balance += amount
        sponsor.total_deposited += amount
        balance_after = sponsor.available_balance

        tx = Transaction(
            entity_type=EntityType.SPONSOR,
            entity_id=sponsor_id,
            tx_type=tx_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=description,
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()
        return tx

    @staticmethod
    async def debit_sponsor_for_campaign(
        session: AsyncSession,
        sponsor_id: int,
        amount: Decimal,
        campaign_id: int,
        idempotency_key: str,
    ) -> Transaction:
        """
        Move funds from sponsor.available_balance to sponsor.reserved_balance
        when funding a campaign.
        """
        existing = await _check_idempotency(session, idempotency_key)
        if existing:
            raise IdempotencyConflictError(f"Already processed: {idempotency_key}")

        try:
            result = await session.execute(
                select(Sponsor)
                .where(Sponsor.id == sponsor_id)
                .with_for_update(nowait=True)
            )
        except Exception as e:
            raise LockConflictError(str(e)) from e

        sponsor = result.scalar_one_or_none()
        if not sponsor:
            raise ValueError(f"Sponsor {sponsor_id} not found")

        if sponsor.available_balance < amount:
            raise InsufficientFundsError(
                f"Sponsor {sponsor_id} available balance {sponsor.available_balance} < {amount}"
            )

        balance_before = sponsor.available_balance
        sponsor.available_balance -= amount
        sponsor.reserved_balance += amount
        balance_after = sponsor.available_balance

        tx = Transaction(
            entity_type=EntityType.SPONSOR,
            entity_id=sponsor_id,
            tx_type=TransactionType.CAMPAIGN_FUND,
            amount=-amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="campaign",
            reference_id=campaign_id,
            description=f"Campaign #{campaign_id} funding",
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()
        return tx

    @staticmethod
    async def release_campaign_budget(
        session: AsyncSession,
        sponsor_id: int,
        amount: Decimal,
        campaign_id: int,
        idempotency_key: str,
        description: str = "Campaign budget release",
    ) -> Transaction:
        """Release unused campaign budget back to sponsor.available_balance."""
        existing = await _check_idempotency(session, idempotency_key)
        if existing:
            raise IdempotencyConflictError(f"Already processed: {idempotency_key}")

        try:
            result = await session.execute(
                select(Sponsor)
                .where(Sponsor.id == sponsor_id)
                .with_for_update(nowait=True)
            )
        except Exception as e:
            raise LockConflictError(str(e)) from e

        sponsor = result.scalar_one_or_none()
        if not sponsor:
            raise ValueError(f"Sponsor {sponsor_id} not found")

        balance_before = sponsor.available_balance
        sponsor.reserved_balance -= amount
        sponsor.available_balance += amount
        balance_after = sponsor.available_balance

        tx = Transaction(
            entity_type=EntityType.SPONSOR,
            entity_id=sponsor_id,
            tx_type=TransactionType.CAMPAIGN_RELEASE,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="campaign",
            reference_id=campaign_id,
            description=description,
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()
        return tx
