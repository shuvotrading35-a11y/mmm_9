"""
Blockchain Service — BSC/web3.py interactions.
Handles USDT deposit verification and USDT payout execution.

Security rules:
- Private key NEVER logged
- All amounts in Decimal, never float
- 12+ confirmations required for deposits
- Gas checked before every payout
- USDT balance checked before every payout
"""
import json
from decimal import Decimal
from typing import Optional

import structlog
from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware
from web3.exceptions import TransactionNotFound

log = structlog.get_logger(__name__)

# BEP-20 / ERC-20 minimal ABI for transfer and balanceOf
ERC20_ABI = json.loads("""[
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "anonymous": false,
        "inputs": [
            {"indexed": true, "name": "from", "type": "address"},
            {"indexed": true, "name": "to", "type": "address"},
            {"indexed": false, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]""")

# USDT on BSC has 18 decimals (unlike Ethereum USDT which has 6)
USDT_DECIMALS = 18


def _wei_to_usdt(amount_wei: int) -> Decimal:
    """Convert USDT amount from smallest unit (18 decimals) to USDT."""
    return Decimal(amount_wei) / Decimal(10 ** USDT_DECIMALS)


def _usdt_to_wei(amount: Decimal) -> int:
    """Convert USDT to smallest unit (18 decimals)."""
    return int(amount * Decimal(10 ** USDT_DECIMALS))


class BlockchainService:

    def __init__(self, rpc_url: str, usdt_contract: str, payout_wallet: str):
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc_url))
        self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)
        self.usdt_contract_address = AsyncWeb3.to_checksum_address(usdt_contract)
        self.payout_wallet = AsyncWeb3.to_checksum_address(payout_wallet)
        self._usdt_contract = None

    def _get_usdt_contract(self):
        if not self._usdt_contract:
            self._usdt_contract = self.w3.eth.contract(
                address=self.usdt_contract_address,
                abi=ERC20_ABI,
            )
        return self._usdt_contract

    async def verify_deposit(
        self,
        tx_hash: str,
        expected_recipient: str,
        min_confirmations: int = 12,
    ) -> dict:
        """
        Verify a BSC USDT deposit transaction.

        Returns:
        {
            "success": bool,
            "amount": Decimal,
            "from_address": str,
            "block_number": int,
            "confirmations": int,
            "error": str (on failure)
        }
        """
        try:
            # Get transaction
            tx = await self.w3.eth.get_transaction(tx_hash)
            if not tx:
                return {"success": False, "error": "Transaction not found"}

            # Get receipt (confirms execution)
            receipt = await self.w3.eth.get_transaction_receipt(tx_hash)
            if not receipt:
                return {"success": False, "error": "Transaction not mined yet"}

            if receipt.status != 1:
                return {"success": False, "error": "Transaction failed on-chain"}

            # Verify recipient is our hot wallet
            recipient = AsyncWeb3.to_checksum_address(expected_recipient)

            # Parse ERC-20 Transfer event from logs
            contract = self._get_usdt_contract()
            transfer_events = contract.events.Transfer().process_receipt(receipt)

            usdt_amount = Decimal("0")
            from_address = None

            for event in transfer_events:
                to_addr = AsyncWeb3.to_checksum_address(event["args"]["to"])
                if to_addr == recipient:
                    # Check token contract
                    if AsyncWeb3.to_checksum_address(receipt["to"]) == self.usdt_contract_address:
                        usdt_amount += _wei_to_usdt(event["args"]["value"])
                        from_address = event["args"]["from"]

            if usdt_amount <= Decimal("0"):
                return {
                    "success": False,
                    "error": "No USDT transfer to platform wallet found in transaction",
                }

            # Check confirmations
            current_block = await self.w3.eth.block_number
            confirmations = current_block - receipt.blockNumber

            if confirmations < min_confirmations:
                return {
                    "success": False,
                    "error": f"Only {confirmations} confirmations, need {min_confirmations}",
                    "confirmations": confirmations,
                    "block_number": receipt.blockNumber,
                    "amount": usdt_amount,
                    "from_address": from_address,
                }

            return {
                "success": True,
                "amount": usdt_amount,
                "from_address": from_address,
                "block_number": receipt.blockNumber,
                "confirmations": confirmations,
            }

        except TransactionNotFound:
            return {"success": False, "error": "Transaction not found on BSC"}
        except Exception as e:
            log.error("Deposit verification error", tx_hash=tx_hash, error=str(e))
            return {"success": False, "error": f"Verification error: {type(e).__name__}"}

    async def get_usdt_balance(self, address: str) -> Decimal:
        """Get USDT balance of an address."""
        contract = self._get_usdt_contract()
        checksum_addr = AsyncWeb3.to_checksum_address(address)
        raw_balance = await contract.functions.balanceOf(checksum_addr).call()
        return _wei_to_usdt(raw_balance)

    async def get_bnb_balance(self, address: str) -> Decimal:
        """Get BNB balance of an address (for gas)."""
        checksum_addr = AsyncWeb3.to_checksum_address(address)
        wei = await self.w3.eth.get_balance(checksum_addr)
        return Decimal(self.w3.from_wei(wei, "ether"))

    async def send_usdt(
        self,
        to_address: str,
        amount: Decimal,
        private_key: str,
        idempotency_key: str,
    ) -> dict:
        """
        Send USDT from payout wallet to destination.
        Returns {"success": bool, "tx_hash": str, "gas_used": int, "error": str}

        NEVER logs private_key.
        """
        try:
            to_addr = AsyncWeb3.to_checksum_address(to_address)
            contract = self._get_usdt_contract()
            amount_wei = _usdt_to_wei(amount)

            # Safety checks before broadcast
            usdt_bal = await self.get_usdt_balance(self.payout_wallet)
            if usdt_bal < amount:
                return {
                    "success": False,
                    "error": f"Insufficient USDT balance: {usdt_bal} < {amount}",
                }

            bnb_bal = await self.get_bnb_balance(self.payout_wallet)
            if bnb_bal < Decimal("0.001"):
                return {
                    "success": False,
                    "error": f"Insufficient BNB for gas: {bnb_bal}",
                }

            # Build transaction
            nonce = await self.w3.eth.get_transaction_count(self.payout_wallet)
            gas_price = await self.w3.eth.gas_price
            # Add 10% to gas price for faster inclusion
            gas_price = int(gas_price * 1.1)

            tx_params = {
                "from": self.payout_wallet,
                "nonce": nonce,
                "gasPrice": gas_price,
            }

            # Estimate gas
            try:
                gas_estimate = await contract.functions.transfer(
                    to_addr, amount_wei
                ).estimate_gas(tx_params)
                tx_params["gas"] = int(gas_estimate * 1.2)  # 20% buffer
            except Exception as e:
                return {"success": False, "error": f"Gas estimation failed: {e}"}

            # Build + sign
            tx = await contract.functions.transfer(to_addr, amount_wei).build_transaction(tx_params)
            signed = self.w3.eth.account.sign_transaction(tx, private_key=private_key)

            # Broadcast
            tx_hash = await self.w3.eth.send_raw_transaction(signed.rawTransaction)
            tx_hash_hex = tx_hash.hex()

            log.info(
                "USDT transfer broadcast",
                to=to_address,
                amount=str(amount),
                tx_hash=tx_hash_hex,
                # private_key NEVER logged
            )

            # Wait for receipt (with timeout)
            receipt = await self.w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=120, poll_latency=3
            )

            if receipt.status != 1:
                return {
                    "success": False,
                    "tx_hash": tx_hash_hex,
                    "error": "Transaction reverted on-chain",
                }

            return {
                "success": True,
                "tx_hash": tx_hash_hex,
                "gas_used": receipt.gasUsed,
                "block_number": receipt.blockNumber,
            }

        except Exception as e:
            log.error(
                "USDT send failed",
                to=to_address,
                amount=str(amount),
                error=str(e),
                # Never include private_key in log
            )
            return {"success": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    async def get_block_number(self) -> int:
        """Get current BSC block number."""
        return await self.w3.eth.block_number


def get_blockchain_service() -> BlockchainService:
    """Singleton factory."""
    from config import settings
    return BlockchainService(
        rpc_url=settings.BSC_RPC_URL,
        usdt_contract=settings.USDT_CONTRACT_ADDRESS,
        payout_wallet=settings.PAYOUT_WALLET_ADDRESS,
    )
