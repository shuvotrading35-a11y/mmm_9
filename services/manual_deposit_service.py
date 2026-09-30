"""Manual deposit service — Binance Pay & BEP20 (admin-reviewed)."""
import time
import uuid
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

log = structlog.get_logger(__name__)


class ManualDepositService:

    @staticmethod
    async def create_binance_pay_deposit(session, sponsor_id, amount):
        from models.deposit import Deposit, DepositStatus

        if not settings.BINANCE_PAY_ID:
            raise ValueError("BINANCE_PAY_ID not configured")

        # Unique client ref (in case we need it for tracking later)
        client_ref = f"BNB{sponsor_id}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        dep = Deposit(
            sponsor_id=sponsor_id,
            amount=amount,
            network="BINANCE_PAY",
            status=DepositStatus.PENDING,
            payment_method="BINANCE_PAY",
            deposit_address=settings.BINANCE_PAY_ID,
        )
        session.add(dep)
        await session.flush()

        log.info(
            "Binance deposit created",
            deposit_id=dep.id,
            sponsor_id=sponsor_id,
            amount=str(amount),
            client_ref=client_ref,
        )
        return {
            "deposit_id": dep.id,
            "binance_pay_id": settings.BINANCE_PAY_ID,
            "amount": amount,
        }

    @staticmethod
    async def create_bep20_deposit(session, sponsor_id, amount):
        from models.deposit import Deposit, DepositStatus

        if not settings.BEP20_DEPOSIT_ADDRESS:
            raise ValueError("BEP20_DEPOSIT_ADDRESS not configured")

        client_ref = f"BEP{sponsor_id}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        dep = Deposit(
            sponsor_id=sponsor_id,
            amount=amount,
            network="BSC",
            status=DepositStatus.PENDING,
            payment_method="BEP20",
            deposit_address=settings.BEP20_DEPOSIT_ADDRESS,
        )
        session.add(dep)
        await session.flush()

        log.info(
            "BEP20 deposit created",
            deposit_id=dep.id,
            sponsor_id=sponsor_id,
            amount=str(amount),
            client_ref=client_ref,
        )
        return {
            "deposit_id": dep.id,
            "address": settings.BEP20_DEPOSIT_ADDRESS,
            "amount": amount,
        }

    @staticmethod
    async def attach_screenshot(session, deposit_id, file_id):
        from models.deposit import Deposit, DepositStatus

        dep = await session.get(Deposit, deposit_id)
        if not dep or dep.status != DepositStatus.PENDING:
            return False

        dep.user_screenshot_file_id = file_id
        await session.flush()
        await ManualDepositService._notify_admin_review(dep)
        return True

    @staticmethod
    async def attach_tx_hash(session, deposit_id, tx_hash):
        from models.deposit import Deposit, DepositStatus

        tx_hash = (tx_hash or "").strip().lower()
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            return False

        dep = await session.get(Deposit, deposit_id)
        if not dep or dep.status != DepositStatus.PENDING:
            return False

        dep.user_submitted_tx_hash = tx_hash
        await session.flush()
        await ManualDepositService._notify_admin_review(dep)
        return True

    @staticmethod
    async def _notify_admin_review(dep):
        """Send review request to all admins with approve/reject buttons."""
        try:
            from services.notification_service import NotificationService
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            bot = NotificationService._ensure_bot()
            if not bot:
                log.warning("Cannot notify admins — no bot instance")
                return

            # Lookup sponsor info for context
            sponsor_info = ""
            try:
                from database import get_session
                from models.sponsor import Sponsor
                from models.user import User

                async with get_session() as s:
                    sp = await s.get(Sponsor, dep.sponsor_id)
                    if sp:
                        u = await s.get(User, sp.user_id)
                        if u:
                            uname = f"@{u.username}" if u.username else (u.first_name or "user")
                            sponsor_info = f"{uname} (<code>{sp.user_id}</code>)"
            except Exception:
                log.exception("Failed to lookup sponsor info for review notify")

            caption = (
                f"💰 <b>New Manual Deposit — Review Needed</b>\n\n"
                f"📌 Deposit: <b>#{dep.id}</b>\n"
                f"👤 Sponsor: {sponsor_info or '—'}\n"
                f"💵 Amount: <b>{dep.amount} USDT</b>\n"
                f"📥 Method: <b>{dep.payment_method}</b>\n"
            )
            if dep.deposit_address:
                caption += f"🎯 To: <code>{dep.deposit_address}</code>\n"
            if dep.user_submitted_tx_hash:
                caption += f"🔗 TX: <code>{dep.user_submitted_tx_hash}</code>\n"

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"dep_approve:{dep.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"dep_reject:{dep.id}"),
            ]])

            for admin_id in settings.ADMIN_IDS:
                try:
                    if dep.user_screenshot_file_id:
                        await bot.send_photo(
                            chat_id=admin_id,
                            photo=dep.user_screenshot_file_id,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=kb,
                        )
                    else:
                        await bot.send_message(
                            chat_id=admin_id,
                            text=caption,
                            parse_mode="HTML",
                            reply_markup=kb,
                        )
                except Exception:
                    log.exception("Admin deposit notify failed", admin_id=admin_id)

        except Exception:
            log.exception("Deposit admin notify outer failed")

    @staticmethod
    async def approve_deposit(session, deposit_id, admin_id):
        from models.deposit import Deposit, DepositStatus
        from models.sponsor import Sponsor
        from datetime import datetime, timezone

        dep = await session.get(Deposit, deposit_id)
        if not dep:
            log.warning("Deposit not found", deposit_id=deposit_id)
            return False
        if dep.status != DepositStatus.PENDING:
            log.warning(
                "Deposit not in PENDING state",
                deposit_id=deposit_id,
                status=dep.status,
            )
            return False

        sponsor = await session.get(Sponsor, dep.sponsor_id)
        if not sponsor:
            log.error(
                "Sponsor not found for deposit",
                deposit_id=deposit_id,
                sponsor_id=dep.sponsor_id,
            )
            return False

        amount = Decimal(str(dep.amount))
        sponsor.available_balance = (sponsor.available_balance or Decimal("0")) + amount
        sponsor.total_deposited = (sponsor.total_deposited or Decimal("0")) + amount

        now = datetime.now(tz=timezone.utc)
        dep.status = DepositStatus.CONFIRMED
        dep.reviewed_by = admin_id
        dep.reviewed_at = now
        dep.credited_at = now
        await session.flush()

        log.info(
            "Manual deposit approved",
            deposit_id=dep.id,
            admin_id=admin_id,
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
            log.exception("Deposit approve notify failed")

        return True

    @staticmethod
    async def reject_deposit(session, deposit_id, admin_id, reason="Rejected by admin"):
        from models.deposit import Deposit, DepositStatus
        from models.sponsor import Sponsor
        from datetime import datetime, timezone

        dep = await session.get(Deposit, deposit_id)
        if not dep:
            return False
        if dep.status != DepositStatus.PENDING:
            return False

        dep.status = DepositStatus.FAILED
        dep.reviewed_by = admin_id
        dep.reviewed_at = datetime.now(tz=timezone.utc)
        dep.rejection_reason = (reason or "")[:500]
        await session.flush()

        log.info(
            "Manual deposit rejected",
            deposit_id=dep.id,
            admin_id=admin_id,
            reason=reason,
        )

        # Notify sponsor
        try:
            sponsor = await session.get(Sponsor, dep.sponsor_id)
            if sponsor:
                from services.notification_service import NotificationService
                await NotificationService.send_to_user(
                    sponsor.user_id,
                    f"❌ <b>Deposit Rejected</b>\n\n"
                    f"💵 Amount: <b>{dep.amount} USDT</b>\n"
                    f"📝 Reason: {reason[:200]}",
                )
        except Exception:
            log.exception("Deposit reject notify failed")

        return True