"""
Rate Limit Middleware — Redis sliding window per user.
"""
import time
from typing import Optional

import structlog
from database import get_redis

log = structlog.get_logger(__name__)


class RateLimitMiddleware:

    @staticmethod
    async def check(
        user_id: int,
        action: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        """
        Returns True if allowed, False if rate limited.
        Uses Redis sorted set sliding window algorithm.
        """
        redis = get_redis()
        key = f"rate:{action}:{user_id}"
        now = time.time()
        window_start = now - window_seconds

        pipe = redis.pipeline()
        # Remove old entries outside the window
        pipe.zremrangebyscore(key, "-inf", window_start)
        # Count current entries in window
        pipe.zcard(key)
        # Add current request
        pipe.zadd(key, {str(now): now})
        # Set expiry
        pipe.expire(key, window_seconds + 1)

        results = await pipe.execute()
        count = results[1]  # Count before adding current

        if count >= limit:
            log.info(
                "Rate limit exceeded",
                user_id=user_id,
                action=action,
                count=count,
                limit=limit,
            )
            return False

        return True

    @staticmethod
    async def get_remaining(
        user_id: int,
        action: str,
        limit: int,
        window_seconds: int,
    ) -> int:
        """Get remaining allowed requests in the current window."""
        redis = get_redis()
        key = f"rate:{action}:{user_id}"
        now = time.time()
        window_start = now - window_seconds

        await redis.zremrangebyscore(key, "-inf", window_start)
        count = await redis.zcard(key)
        return max(0, limit - count)

    @staticmethod
    async def check_task_verify(user_id: int) -> bool:
        from config import settings
        return await RateLimitMiddleware.check(
            user_id, "task_verify",
            settings.RATE_TASK_VERIFY_LIMIT,
            settings.RATE_TASK_VERIFY_WINDOW,
        )

    @staticmethod
    async def check_withdrawal(user_id: int) -> bool:
        from config import settings
        return await RateLimitMiddleware.check(
            user_id, "withdraw",
            settings.RATE_WITHDRAW_LIMIT,
            settings.RATE_WITHDRAW_WINDOW,
        )

    @staticmethod
    async def check_support(user_id: int) -> bool:
        from config import settings
        return await RateLimitMiddleware.check(
            user_id, "support",
            settings.RATE_SUPPORT_LIMIT,
            settings.RATE_SUPPORT_WINDOW,
        )

    @staticmethod
    async def check_start(user_id: int) -> bool:
        from config import settings
        return await RateLimitMiddleware.check(
            user_id, "start",
            settings.RATE_START_LIMIT,
            settings.RATE_START_WINDOW,
        )
