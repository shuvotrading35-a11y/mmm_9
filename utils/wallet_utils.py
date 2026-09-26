"""
Wallet Utils — BSC address validation.
"""
from typing import Optional


def validate_bsc_address(address: str) -> bool:
    """
    Validate a BSC/Ethereum address. Accepts checksummed, lowercase,
    or uppercase forms — only checks structure (0x + 40 hex chars).
    """
    if not address:
        return False

    s = address.strip()
    if len(s) != 42 or not s.startswith("0x"):
        return False

    # Must be hex after 0x
    try:
        int(s[2:], 16)
    except ValueError:
        return False

    # Optional: prefer web3's validator when available
    try:
        from web3 import Web3
        return Web3.is_address(s)
    except Exception:
        return True


def checksum_address(address: str) -> str:
    """Return EIP-55 checksummed version of address."""
    try:
        from web3 import Web3
        return Web3.to_checksum_address(address.strip())
    except Exception:
        return address.strip()


def mask_wallet(address: str) -> str:
    """Mask wallet for display: 0x1234...abcd"""
    if not address or len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"