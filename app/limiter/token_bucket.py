"""Redis-backed token bucket rate limiter.

Concept:
- Each user has a bucket of tokens.
- Tokens refill at a steady rate over time.
- Each request consumes one token.
- Empty bucket means the request is denied.

Redis storage:
- Key: rate:token:{user_id}
- Hash fields:
  - tokens: current token count stored as a string
  - last_refill: unix timestamp of the last refill stored as a string

Why Redis is used here:
- The bucket state must be shared across app instances.
- Redis keeps the token counts consistent even when multiple servers handle traffic.
"""

from __future__ import annotations

import math
import time
from typing import Dict

import redis

from app.config.settings import settings
from app.limiter.redis_client import redis_client


class RedisTokenBucketLimiter:
	def __init__(self, redis_client: redis.Redis, capacity: int, refill_rate: float) -> None:
		self.redis_client = redis_client
		self.capacity = float(capacity)
		self.refill_rate = float(refill_rate)

	def _key(self, user_id: str) -> str:
		return f"rate:token:{user_id}"

	def _seconds_until(self, current_tokens: float, target_tokens: float) -> int:
		"""Estimate how long until a target token level is reached."""
		if self.refill_rate <= 0:
			return 0

		missing_tokens = max(0.0, target_tokens - current_tokens)
		return int(math.ceil(missing_tokens / self.refill_rate))

	def allow_request(self, user_id: str) -> Dict[str, object]:
		"""Allow or deny a request using a Redis-backed token bucket.

		The method uses a Redis pipeline with WATCH/MULTI so the read-modify-write
		cycle is safe under concurrent access from multiple app instances.
		"""

		key = self._key(user_id)

		while True:
			pipe = self.redis_client.pipeline()
			try:
				pipe.watch(key)

				bucket = pipe.hgetall(key)
				now = time.time()

				# First request for this user: initialize the bucket at full capacity.
				current_tokens = float(bucket.get("tokens", self.capacity))
				last_refill = float(bucket.get("last_refill", now))

				elapsed = max(0.0, now - last_refill)
				refill = elapsed * self.refill_rate
				new_tokens = min(self.capacity, current_tokens + refill)

				allowed = new_tokens >= 1.0
				if allowed:
					updated_tokens = new_tokens - 1.0
				else:
					updated_tokens = new_tokens

				# Store floats as strings because Redis hashes are string based.
				pipe.multi()
				pipe.hset(
					key,
					mapping={
						"tokens": str(updated_tokens),
						"last_refill": str(now),
					},
				)
				pipe.execute()
				break
			except redis.WatchError:
				# Another writer updated the bucket while we were reading it.
				# Retry with the latest values.
				continue
			finally:
				pipe.reset()

		remaining = round(updated_tokens, 2)
		reset_in = self._seconds_until(updated_tokens, self.capacity)

		if allowed:
			return {
				"allowed": True,
				"remaining": remaining,
				"retry_after": 0,
				"reset_in": reset_in,
			}

		retry_after = self._seconds_until(updated_tokens, min(self.capacity, updated_tokens + 1.0))
		return {
			"allowed": False,
			"remaining": remaining,
			"retry_after": retry_after,
			"reset_in": reset_in,
		}


# Convenience instance aligned with the app's current settings.
token_bucket_limiter = RedisTokenBucketLimiter(
	redis_client=redis_client,
	capacity=settings.RATE_LIMIT_REQUESTS,
	refill_rate=(settings.RATE_LIMIT_REQUESTS / settings.RATE_LIMIT_WINDOW_SECONDS)
	if settings.RATE_LIMIT_WINDOW_SECONDS > 0
	else 0.0,
)
