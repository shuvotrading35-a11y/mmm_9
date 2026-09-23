"""
Idempotency — Redis-backed idempotency key management.
"""
import hashlib
from typing import Optional

from database import get_redis


async def check_and_set_idempotency(key: str, ttl_seconds: int = 3600) -> bool:
    """
    Returns True if key is new (safe to proceed).
    Returns False if key already exists (duplicate — skip).
    Sets key with TTL atomically using SET NX.
    """
    redis = get_redis()
    result = await redis.set(f"idem:{key}", "1", nx=True, ex=ttl_seconds)
    return result is not None


def make_key(*parts) -> str:
    """Generate a deterministic idempotency key from parts."""
    from config import settings
    raw = ":".join(str(p) for p in parts) + f":{settings.SECRET_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


"""
Pagination — inline keyboard pagination helper.
"""
from typing import List, TypeVar, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

T = TypeVar("T")


def paginate(items: List[T], page: int, page_size: int = 10) -> Tuple[List[T], int, int]:
    """
    Paginate a list. Returns (page_items, total_pages, current_page).
    Page is 0-indexed.
    """
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    end = start + page_size
    return items[start:end], total_pages, page


def pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
) -> List[List[InlineKeyboardButton]]:
    """Build prev/next navigation row."""
    if total_pages <= 1:
        return []

    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton(
            "⬅️ Prev", callback_data=f"{callback_prefix}:{current_page - 1}"
        ))
    buttons.append(InlineKeyboardButton(
        f"{current_page + 1}/{total_pages}", callback_data="noop"
    ))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton(
            "Next ➡️", callback_data=f"{callback_prefix}:{current_page + 1}"
        ))
    return [buttons]
