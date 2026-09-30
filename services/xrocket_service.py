"""
xRocket Pay API integration.

Covers:
  - Withdrawals (external wallet)
  - Invoices (deposits)
  - Mass payouts (batch rewards)
  - Cheques (gift links)

NOT covered: single user-to-user payout (intentionally excluded).
"""
import asyncio
import uuid
from decimal import Decimal
from typing import Any, Optional

import aiohttp
import structlog

from config import settings

log = structlog.get_logger(__name__)

PROD_BASE = "https://pay.api.xrocket.exchange"
TESTNET_BASE = "https://pay.api.testnet.xrocket.exchange"


class XRocketError(Exception):
    """Raised for any xRocket API error with structured info."""

    def __init__(self, status: int, problem: dict):
        self.status = status
        self.problem = problem or {}
        self.type = self.problem.get("type", "")
        self.kind = self.problem.get("kind", "")
        self.detail = self.problem.get("detail", "")
        super().__init__(f"[{self.status}] {self.type}: {self.detail}")


class XRocketService:
    _session: Optional[aiohttp.ClientSession] = None

    # ──────────────────────────────────────────────────────────
    # HTTP plumbing
    # ──────────────────────────────────────────────────────────
    @classmethod
    def _base_url(cls) -> str:
        env = getattr(settings, "XROCKET_ENV", "production").lower()
        return TESTNET_BASE if env == "testnet" else PROD_BASE

    @classmethod
    def _token(cls) -> Optional[str]:
        return getattr(settings, "XROCKET_API_TOKEN", None)

    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            cls._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return cls._session

    @classmethod
    async def close(cls) -> None:
        if cls._session and not cls._session.closed:
            await cls._session.close()

    @classmethod
    async def _request(
        cls,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        token = cls._token()
        if not token:
            raise XRocketError(401, {
                "type": "/api/problems/unauthorized",
                "kind": "unauthorized",
                "detail": "XROCKET_API_TOKEN not configured",
            })

        url = f"{cls._base_url()}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        session = await cls._get_session()

        try:
            async with session.request(
                method, url, json=json, params=params, headers=headers
            ) as resp:
                body = await resp.json(content_type=None)
                if 200 <= resp.status < 300:
                    return body if body is not None else {}

                # Error → raise structured
                problem = body if isinstance(body, dict) else {}
                log.warning(
                    "xRocket API error",
                    path=path,
                    status=resp.status,
                    type=problem.get("type"),
                )
                raise XRocketError(resp.status, problem)
        except aiohttp.ClientError as e:
            log.exception("xRocket network error", path=path)
            raise XRocketError(0, {
                "type": "/api/problems/network_error",
                "kind": "internal",
                "detail": str(e),
            })

    @staticmethod
    def _new_client_id(prefix: str) -> str:
        return f"{prefix}{uuid.uuid4().hex[:20]}"

    # ══════════════════════════════════════════════════════════
    # WITHDRAWALS
    # ══════════════════════════════════════════════════════════

    @classmethod
    async def get_withdrawal_quotas(cls) -> dict:
        """GET /api/v1/withdrawals/quotas — min amounts, fees per asset."""
        return await cls._request("GET", "/api/v1/withdrawals/quotas")

    @classmethod
    async def create_withdrawal(
        cls,
        *,
        asset: str,
        network: str,
        address: str,
        amount: Decimal,
        client_withdrawal_id: Optional[str] = None,
        memo: Optional[str] = None,
    ) -> dict:
        """
        POST /api/v1/withdrawals
        clientWithdrawalId is REQUIRED for idempotency.
        """
        payload: dict[str, Any] = {
            "clientWithdrawalId": client_withdrawal_id or cls._new_client_id("WD"),
            "asset": asset,
            "network": network,
            "address": address,
            "amount": str(amount),
        }
        if memo:
            payload["memo"] = memo
        return await cls._request("POST", "/api/v1/withdrawals", json=payload)

    @classmethod
    async def get_withdrawal(cls, withdrawal_id: str) -> dict:
        """GET /api/v1/withdrawal?withdrawalId=..."""
        return await cls._request(
            "GET", "/api/v1/withdrawal", params={"withdrawalId": withdrawal_id}
        )

    @classmethod
    async def get_withdrawal_by_client_id(cls, client_id: str) -> dict:
        """GET /api/v1/withdrawal?clientWithdrawalId=..."""
        return await cls._request(
            "GET",
            "/api/v1/withdrawal",
            params={"clientWithdrawalId": client_id},
        )

    @classmethod
    async def list_withdrawals(cls, **filters) -> dict:
        """GET /api/v1/withdrawals"""
        return await cls._request("GET", "/api/v1/withdrawals", params=filters)

    # ══════════════════════════════════════════════════════════
    # INVOICES  (for sponsor deposits)
    # ══════════════════════════════════════════════════════════

    @classmethod
    async def create_invoice(
        cls,
        *,
        amount: Optional[Decimal] = None,
        asset: str = "USDT",
        price_currency: Optional[str] = None,
        description: Optional[str] = None,
        client_invoice_id: Optional[str] = None,
        expires_in: Optional[int] = None,   # seconds
    ) -> dict:
        """
        POST /api/v1/invoices
        Returns invoice with pay URL for the user.

        `priceCurrency` is REQUIRED by xRocket — it's the currency the
        invoice amount is denominated in. Defaults to `asset` if not set.
        """
        payload: dict[str, Any] = {
            "clientInvoiceId": client_invoice_id or cls._new_client_id("INV"),
            "asset": asset,
            "priceCurrency": price_currency or asset,
        }
        if amount is not None:
            payload["amount"] = str(amount)
        if description:
            payload["description"] = description
        if expires_in:
            payload["expiresIn"] = expires_in
        return await cls._request("POST", "/api/v1/invoices", json=payload)

    @classmethod
    async def get_invoice(cls, invoice_id: str) -> dict:
        return await cls._request(
            "GET", "/api/v1/invoice", params={"invoiceId": invoice_id}
        )

    @classmethod
    async def get_invoice_by_client_id(cls, client_id: str) -> dict:
        return await cls._request(
            "GET", "/api/v1/invoice", params={"clientInvoiceId": client_id}
        )

    @classmethod
    async def list_invoices(cls, **filters) -> dict:
        return await cls._request("GET", "/api/v1/invoices", params=filters)

    @classmethod
    async def get_invoice_payments(cls, invoice_id: str) -> dict:
        return await cls._request(
            "GET",
            "/api/v1/invoice/payments",
            params={"invoiceId": invoice_id},
        )

    @classmethod
    async def delete_invoice(cls, invoice_id: str) -> dict:
        return await cls._request(
            "DELETE", "/api/v1/invoice", params={"invoiceId": invoice_id}
        )

    @classmethod
    async def create_invoice_payment_address(
        cls, *, invoice_id: str, network: str
    ) -> dict:
        """Generate on-chain deposit address for an invoice."""
        return await cls._request(
            "POST",
            "/api/v1/invoice/payment-address",
            json={"invoiceId": invoice_id, "network": network},
        )

    # ══════════════════════════════════════════════════════════
    # MASS PAYOUTS  (batch bonuses)
    # ══════════════════════════════════════════════════════════

    @classmethod
    async def create_mass_payout(
        cls,
        *,
        entries: list[dict],
        asset: str = "USDT",
    ) -> dict:
        """
        POST /api/v1/mass-payouts
        entries: [{"target": "1234567", "targetType": "user_id",
                   "amount": "1.5", "clientPayoutId": "..." }]
        Max 500 entries per request.
        """
        if not (1 <= len(entries) <= 500):
            raise ValueError("mass payout entries must be 1..500")

        # Ensure every entry has a clientPayoutId (idempotency)
        for e in entries:
            if not e.get("clientPayoutId"):
                e["clientPayoutId"] = cls._new_client_id("MP")

        payload = {"asset": asset, "entries": entries}
        return await cls._request("POST", "/api/v1/mass-payouts", json=payload)

    @classmethod
    async def get_mass_payout(cls, mass_payout_id: str) -> dict:
        return await cls._request(
            "GET",
            "/api/v1/mass-payout",
            params={"massPayoutId": mass_payout_id},
        )

    # ══════════════════════════════════════════════════════════
    # CHEQUES  (gift links)
    # ══════════════════════════════════════════════════════════

    @classmethod
    async def create_cheque(
        cls,
        *,
        amount: Decimal,
        asset: str = "USDT",
        description: Optional[str] = None,
        client_cheque_id: Optional[str] = None,
        password: Optional[str] = None,
    ) -> dict:
        """
        POST /api/v1/cheques
        Creates a personal cheque — funds are reserved until claimed/cancelled.
        """
        payload: dict[str, Any] = {
            "clientChequeId": client_cheque_id or cls._new_client_id("CHQ"),
            "asset": asset,
            "amount": str(amount),
        }
        if description:
            payload["description"] = description
        if password:
            payload["password"] = password
        return await cls._request("POST", "/api/v1/cheques", json=payload)

    @classmethod
    async def get_cheque(cls, cheque_id: str) -> dict:
        return await cls._request(
            "GET", "/api/v1/cheque", params={"chequeId": cheque_id}
        )

    @classmethod
    async def get_cheque_by_client_id(cls, client_id: str) -> dict:
        return await cls._request(
            "GET", "/api/v1/cheque", params={"clientChequeId": client_id}
        )

    @classmethod
    async def list_cheques(cls, **filters) -> dict:
        return await cls._request("GET", "/api/v1/cheques", params=filters)

    @classmethod
    async def update_cheque(
        cls, *, cheque_id: str, description: str
    ) -> dict:
        return await cls._request(
            "PATCH",
            "/api/v1/cheque",
            json={"chequeId": cheque_id, "description": description},
        )

    @classmethod
    async def delete_cheque(cls, cheque_id: str) -> dict:
        """Cancel a cheque — reserved funds released."""
        return await cls._request(
            "DELETE", "/api/v1/cheque", params={"chequeId": cheque_id}
        )

    # ══════════════════════════════════════════════════════════
    # APP / CURRENCIES / RATES
    # ══════════════════════════════════════════════════════════

    @classmethod
    async def get_app_info(cls) -> dict:
        return await cls._request("GET", "/api/v1/app-info")

    @classmethod
    async def get_balances(cls) -> dict:
        return await cls._request("GET", "/api/v1/balances")

    @classmethod
    async def get_currencies(cls) -> dict:
        return await cls._request("GET", "/api/v1/currencies")

    @classmethod
    async def get_rates(cls, **params) -> dict:
        return await cls._request("GET", "/api/v1/rates", params=params)