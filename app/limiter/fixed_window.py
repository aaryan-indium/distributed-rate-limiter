"""Redis-backed fixed window rate limiter.

Request flow:
- The API receives a request and extracts X-User-ID.
- This limiter increments the user-specific Redis counter atomically.
- If the counter is within the limit, the request is allowed.
- If the counter exceeds the limit, the request is denied with retry metadata.

Why Redis is the source of truth here:
- The request count lives in Redis, not in Python memory.
- All app instances read and write the same key namespace.
- That makes the decision consistent across multiple servers.
"""

from typing import Dict


class RedisFixedWindowRateLimiter:
    def __init__(self, redis_client, limit: int, window_seconds: int) -> None:
        self.redis_client = redis_client
        self.limit = limit
        self.window_seconds = window_seconds

    def _key(self, user_id: str) -> str:
        return f"rate:fixed:{user_id}"

    def allow_request(self, user_id: str) -> Dict[str, object]:
        key = self._key(user_id)
        count = self.redis_client.incr(key)

        if count == 1:
            self.redis_client.expire(key, self.window_seconds)

        ttl = self.redis_client.ttl(key)
        retry_after = max(0, ttl) if ttl is not None else 0
        remaining = max(0, self.limit - count)

        if count > self.limit:
            return {
                "allowed": False,
                "remaining": 0,
                "retry_after": retry_after,
                "reset_in": retry_after,
            }

        return {
            "allowed": True,
            "remaining": remaining,
            "retry_after": 0,
            "reset_in": retry_after,
        }
