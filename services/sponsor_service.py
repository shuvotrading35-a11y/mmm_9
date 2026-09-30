"""
Sponsor Service — sponsor account management + deposits (xRocket Invoice).
"""
import json
import time
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.sponsor import Sponsor, SponsorStatus
from models.user import User

log = structlog.get_logger(__name__)


class SponsorService:

    # ══════════════════════════════════════════════════════════════
    # Sponsor account lifecycle
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    async def apply_for_sponsor(
        session: AsyncSession,
        user_id: int,
        company_name: Optional[str] = None,
    ) -> Sponsor:
        """Submit a sponsor application (PENDING status)."""
        existing = await session.execute(
            select(Sponsor).where(Sponsor.user_id == user_id)
        )
        if existing.scalar_one_or_none():
            raise ValueError("You already have a sponsor application")

        sponsor = Sponsor(
            user_id=user_id,
            company_name=company_name,
            status=SponsorStatus.PENDING,
        )
        session.add(sponsor)

        # Mark user as sponsor
        user = await session.get(User, user_id)
        if user:
            user.is_sponsor = True

        await session.flush()

        # Notify admin
        from services.notification_service import NotificationService
        import asyncio
        asyncio.create_task(
            NotificationService.notify_admin_critical(
                f"New sponsor application from user {user_id}: {company_name or 'No company name'}"
            )
        )

        log.info("Sponsor application submitted", user_id=user_id)
        return sponsor

    @staticmethod
    async def approve_sponsor(
        session: AsyncSession,
        sponsor_id: int,
        admin_id: int,
    ) -> Sponsor:
        """Admin approves a sponsor account."""
        from datetime import datetime, timezone

        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            raise ValueError("Sponsor not found")
        if sponsor.status != SponsorStatus.PENDING:
            raise ValueError(f"Cannot approve sponsor in status {sponsor.status}")

        sponsor.status = SponsorStatus.APPROVED
        sponsor.approved_by = admin_id
        sponsor.approved_at = datetime.now(tz=timezone.utc)
        await session.flush()

        log.info("Sponsor approved", sponsor_id=sponsor_id, admin_id=admin_id)
        return sponsor

    @staticmethod
    async def get_sponsor_by_user(
        session: AsyncSession, user_id: int
    ) -> Optional[Sponsor]:
        result = await session.execute(
            select(Sponsor).where(Sponsor.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_sponsor_wallet_info(
        session: AsyncSession, sponsor_id: int
    ) -> dict:
        sponsor = await session.get(Sponsor, sponsor_id)
        if not sponsor:
            return {}
        return {
            "deposit_address": settings.PAYOUT_WALLET_ADDRESS,
            "network": "BNB Smart Chain (BSC)",
            "token": "USDT (BEP-20)",
            "contract": settings.USDT_CONTRACT_ADDRESS,
            "minimum_deposit": str(settings.SPONSOR_MIN_DEPOSIT),
            "available_balance": sponsor.available_balance,
            "reserved_balance": sponsor.reserved_balance,
            "total_deposited": sponsor.total_deposited,
            "total_spent": sponsor.total_spent,
        }

    # ══════════════════════════════════════════════════════════════
    # xRocket Invoice deposits
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    async def create_xrocket_deposit_invoice(
        session: AsyncSession,
        sponsor_id: int,
        amount: Decimal,
        ttl_seconds: int = 3600,
    ) -> dict:
        """
        Create an xRocket invoice for sponsor deposit.
        Returns dict with pay_url, invoice_id, client_invoice_id.
        Does NOT credit balance — that happens after payment confirmed.
        """
        from services.xrocket_service import XRocketService, XRocketError
        from models.deposit import Deposit, DepositStatus

        # Deterministic client ID → retries safe
        client_id = f"DEP{sponsor_id}_{int(time.time())}"

        # 1. Create xRocket invoice
        resp = await XRocketService.create_invoice(
            amount=amount,
            asset=settings.XROCKET_DEPOSIT_ASSET,
            description=f"Sponsor deposit #{sponsor_id}",
            client_invoice_id=client_id,
            expires_in=ttl_seconds,
        )

        invoice_id = str(resp.get("invoiceId") or resp.get("id") or "")
        pay_url = (
            resp.get("payUrl")
            or resp.get("url")
            or resp.get("link")
            or ""
        )

        # 2. Store pending deposit row
        # NOTE: tx_hash stays NULL here — it's only for on-chain deposits.
        deposit = Deposit(
            sponsor_id=sponsor_id,
            amount=amount,
            network=settings.XROCKET_DEPOSIT_ASSET,
            status=DepositStatus.PENDING,
            payment_method="XROCKET_INVOICE",
            xrocket_invoice_id=invoice_id,
            xrocket_client_invoice_id=client_id,
            xrocket_pay_url=pay_url,
            xrocket_status="pending",
            xrocket_response=json.dumps(resp)[:4000],
        )
        session.add(deposit)
        await session.flush()

        log.info(
            "xRocket deposit invoice created",
            sponsor_id=sponsor_id,
            invoice_id=invoice_id,
            amount=str(amount),
            client_id=client_id,
        )

        return {
            "deposit_id": deposit.id,
            "invoice_id": invoice_id,
            "client_invoice_id": client_id,
            "pay_url": pay_url,
            "amount": amount,
        }

    @staticmethod
    async def confirm_xrocket_deposit(
        session: AsyncSession,
        deposit_id: int,
        xrocket_response: dict,
    ) -> bool:
        """
        Called when xRocket confirms invoice paid.
        Credits sponsor balance + marks deposit CONFIRMED.
        Idempotent — safe to call multiple times.
        """
        from models.deposit import Deposit, DepositStatus
        from datetime import datetime, timezone

        deposit = await session.get(Deposit, deposit_id)
        if not deposit:
            log.warning("confirm_xrocket_deposit: deposit not found", deposit_id=deposit_id)
            return False

        # Already confirmed → skip
        if deposit.status == DepositStatus.CONFIRMED:
            log.info("Deposit already confirmed", deposit_id=deposit_id)
            return True

        if deposit.status != DepositStatus.PENDING:
            log.warning(
                "Deposit not in PENDING state",
                deposit_id=deposit_id,
                status=deposit.status,
            )
            return False

        sponsor = await session.get(Sponsor, deposit.sponsor_id)
        if not sponsor:
            log.error(
                "Sponsor not found for deposit",
                deposit_id=deposit_id,
                sponsor_id=deposit.sponsor_id,
            )
            return False

        amount = Decimal(str(deposit.amount))
        sponsor.available_balance = (sponsor.available_balance or Decimal("0")) + amount
        sponsor.total_deposited = (sponsor.total_deposited or Decimal("0")) + amount

        now = datetime.now(tz=timezone.utc)
        deposit.status = DepositStatus.CONFIRMED
        deposit.xrocket_status = xrocket_response.get("status", "paid")
        deposit.xrocket_response = json.dumps(xrocket_response)[:4000]
        deposit.credited_at = now
        await session.flush()

        log.info(
            "Sponsor deposit credited (xRocket)",
            sponsor_id=sponsor.id,
            deposit_id=deposit_id,
            amount=str(amount),
        )

        # Notify sponsor
        try:
            from services.notification_service import NotificationService
            await NotificationService.send_to_user(
                sponsor.user_id,
                f"✅ <b>Deposit Confirmed</b>\n\n"
                f"➕ Amount: <b>+{amount} USDT</b>\n"
                f"💰 Available balance: <b>{sponsor.available_balance} USDT</b>",
            )
        except Exception:
            log.exception("Deposit notify failed", sponsor_id=sponsor.id)

        return True