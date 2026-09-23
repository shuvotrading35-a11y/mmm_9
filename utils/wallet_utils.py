"""
Wallet Utils — BSC address validation with EIP-55 checksum enforcement.
"""
from typing import Optional


def validate_bsc_address(address: str) -> bool:
    """Validate a BSC/Ethereum address with EIP-55 checksum."""
    if not address:
        return False
    try:
        from web3 import Web3
        # This will raise if invalid or wrong checksum
        checksummed = Web3.to_checksum_address(address)
        return bool(checksummed)
    except (ValueError, Exception):
        return False


def checksum_address(address: str) -> str:
    """Return EIP-55 checksummed version of address."""
    from web3 import Web3
    return Web3.to_checksum_address(address)


def mask_wallet(address: str) -> str:
    """Mask wallet for display: 0x1234...abcd"""
    if not address or len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"
