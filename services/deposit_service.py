"""
Deposit Service — BSC USDT deposit verification and crediting.
"""
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.deposit import Deposit, DepositStatus
from models.sponsor import Sponsor, SponsorStatus
from models.transaction import TransactionType
from services.ledger_service import LedgerService, IdempotencyConflictError
from services.blockchain_service import get_blockchain_service

log = structlog.get_logger(__name__)


class DepositService:

    @staticmethod
    async def submit_deposit(
        session: AsyncSession,
        sponsor_id: int,
        tx_hash: str,
    ) -> dict:
        """
        Sponsor submits a TX hash for verification.
        Returns status dict with result.
        """
        # Normalize hash
        tx_hash = tx_hash.strip().lower()
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash

        # Check for duplicate
        existing = await session.execute(
            select(Deposit).where(Deposit.tx_hash == tx_hash)
        )
        if existing.scalar_one_or_none():
            return {"success": False, "error": "This transaction has already been submitted"}

        # Verify sponsor exists and is approved
        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            return {"success": False, "error": "Sponsor account not found"}
        if sponsor.status != SponsorStatus.APPROVED:
            return {"success": False, "error": "Sponsor account not approved"}

        # Create pending deposit record
        deposit = Deposit(
            sponsor_id=sponsor_id,
            amount=Decimal("0"),  # Will be filled after verification
            tx_hash=tx_hash,
            status=DepositStatus.PENDING,
        )
        session.add(deposit)
        await session.flush()

        # Verify on-chain
        blockchain = get_blockchain_service()
        result = await blockchain.verify_deposit(
            tx_hash=tx_hash,
            expected_recipient=settings.PAYOUT_WALLET_ADDRESS,
            min_confirmations=settings.MIN_DEPOSIT_CONFIRMATIONS,
        )

        if not result["success"]:
            # Keep as PENDING if it's a confirmation issue (not yet enough blocks)
            if "confirmations" in result:
                deposit.amount = result.get("amount", Decimal("0"))
                deposit.from_address = result.get("from_address")
                deposit.block_number = result.get("block_number")
                deposit.confirmations = result.get("confirmations", 0)
                await session.flush()
                return {
                    "success": False,
                    "pending": True,
                    "error": result["error"],
                    "confirmations": result.get("confirmations", 0),
                    "required": settings.MIN_DEPOSIT_CONFIRMATIONS,
                }

            deposit.status = DepositStatus.FAILED
            await session.flush()
            return {"success": False, "error": result["error"]}

        # Credit sponsor
        amount = result["amount"]
        if amount < settings.SPONSOR_MIN_DEPOSIT:
            deposit.status = DepositStatus.FAILED
            await session.flush()
            return {
                "success": False,
                "error": f"Deposit {amount} USDT is below minimum {settings.SPONSOR_MIN_DEPOSIT} USDT",
            }

        deposit.amount = amount
        deposit.from_address = result["from_address"]
        deposit.block_number = result["block_number"]
        deposit.confirmations = result["confirmations"]

        import hashlib
        credit_key = hashlib.sha256(
            f"deposit_credit:{tx_hash}:{settings.SECRET_SALT}".encode()
        ).hexdigest()

        try:
            await LedgerService.credit_sponsor(
                session=session,
                sponsor_id=sponsor_id,
                amount=amount,
                tx_type=TransactionType.DEPOSIT,
                idempotency_key=credit_key,
                description=f"USDT deposit via BSC tx {tx_hash[:16]}...",
            )
            deposit.status = DepositStatus.CONFIRMED
            deposit.credited_at = datetime.now(tz=timezone.utc)
            await session.flush()

            log.info(
                "Deposit confirmed and credited",
                sponsor_id=sponsor_id,
                amount=str(amount),
                tx_hash=tx_hash,
            )

            # Notify sponsor
            from services.notification_service import NotificationService
            import asyncio
            asyncio.create_task(
                NotificationService.deposit_confirmed(sponsor_id, amount)
            )

            return {"success": True, "amount": amount, "tx_hash": tx_hash}

        except IdempotencyConflictError:
            return {"success": False, "error": "Deposit already credited"}
        except Exception as e:
            deposit.status = DepositStatus.FAILED
            await session.flush()
            log.error("Deposit credit failed", error=str(e), tx_hash=tx_hash)
            return {"success": False, "error": "Deposit processing error. Contact support."}

    @staticmethod
    async def check_pending_deposits(session: AsyncSession) -> int:
        """
        Background job: Check all PENDING deposits for confirmation.
        Returns count of newly confirmed deposits.
        """
        result = await session.execute(
            select(Deposit).where(Deposit.status == DepositStatus.PENDING)
        )
        pending = result.scalars().all()
        confirmed_count = 0

        blockchain = get_blockchain_service()

        for deposit in pending:
            result = await blockchain.verify_deposit(
                tx_hash=deposit.tx_hash,
                expected_recipient=settings.PAYOUT_WALLET_ADDRESS,
                min_confirmations=settings.MIN_DEPOSIT_CONFIRMATIONS,
            )

            if result["success"]:
                import hashlib
                credit_key = hashlib.sha256(
                    f"deposit_credit:{deposit.tx_hash}:{settings.SECRET_SALT}".encode()
                ).hexdigest()

                try:
                    await LedgerService.credit_sponsor(
                        session=session,
                        sponsor_id=deposit.sponsor_id,
                        amount=result["amount"],
                        tx_type=TransactionType.DEPOSIT,
                        idempotency_key=credit_key,
                        description=f"USDT deposit confirmed",
                    )
                    deposit.status = DepositStatus.CONFIRMED
                    deposit.amount = result["amount"]
                    deposit.confirmations = result["confirmations"]
                    deposit.credited_at = datetime.now(tz=timezone.utc)
                    confirmed_count += 1
                except IdempotencyConflictError:
                    deposit.status = DepositStatus.CONFIRMED
            else:
                deposit.confirmations = result.get("confirmations", deposit.confirmations)

        await session.flush()
        return confirmed_count
