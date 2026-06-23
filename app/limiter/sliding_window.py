"""Redis-backed sliding window counter rate limiter.

This limiter smooths traffic across window boundaries by blending the previous
window count into the current decision using a linear weight.
"""

from __future__ import annotations

import math
import time
from typing import Dict

import redis

from app.config.settings import settings
from app.limiter.redis_client import redis_client


class RedisSlidingWindowLimiter:
	def __init__(self, redis_client: redis.Redis, limit: int, window_seconds: int) -> None:
		self.redis_client = redis_client
		self.limit = limit
		self.window_seconds = window_seconds

	def _prev_key(self, user_id: str) -> str:
		return f"rate:sliding:{user_id}:prev"

	def _curr_key(self, user_id: str) -> str:
		return f"rate:sliding:{user_id}:curr"

	def _window_key(self, user_id: str) -> str:
		return f"rate:sliding:{user_id}:window_start"

	def _window_start_for(self, now: float) -> float:
		return math.floor(now / self.window_seconds) * self.window_seconds

	def _effective_count(self, prev_count: float, curr_count: float, window_start: float, now: float) -> float:
		elapsed_fraction = (now - window_start) / self.window_seconds
		elapsed_fraction = min(max(elapsed_fraction, 0.0), 1.0)
		return prev_count * (1.0 - elapsed_fraction) + curr_count

	def _retry_after(self, effective_count: float) -> int:
		if effective_count < self.limit:
			return 0

		# Conservative estimate required by the spec.
		return 1

	def allow_request(self, user_id: str) -> Dict[str, object]:
		now = time.time()
		prev_key = self._prev_key(user_id)
		curr_key = self._curr_key(user_id)
		window_key = self._window_key(user_id)

		read_pipe = self.redis_client.pipeline()
		read_pipe.get(prev_key)
		read_pipe.get(curr_key)
		read_pipe.get(window_key)
		prev_raw, curr_raw, window_start_raw = read_pipe.execute()

		prev_count = float(prev_raw) if prev_raw is not None else 0.0
		curr_count = float(curr_raw) if curr_raw is not None else 0.0
		window_start = float(window_start_raw) if window_start_raw is not None else None

		if window_start is None:
			window_start = self._window_start_for(now)
			prev_count = 0.0
			curr_count = 0.0
		elif now >= window_start + self.window_seconds:
			prev_count = curr_count
			curr_count = 0.0
			window_start = self._window_start_for(now)

		effective_count = self._effective_count(prev_count, curr_count, window_start, now)
		remaining = max(0.0, round(self.limit - (effective_count + 1), 2))
		reset_in = max(0, int(math.ceil((window_start + self.window_seconds) - now)))

		if effective_count >= self.limit:
			return {
				"allowed": False,
				"remaining": remaining,
				"retry_after": self._retry_after(effective_count),
				"reset_in": reset_in,
			}

		curr_count += 1.0

		write_pipe = self.redis_client.pipeline()
		write_pipe.set(prev_key, str(prev_count), ex=2 * self.window_seconds)
		write_pipe.set(curr_key, str(curr_count), ex=2 * self.window_seconds)
		write_pipe.set(window_key, str(window_start), ex=2 * self.window_seconds)
		write_pipe.execute()

		return {
			"allowed": True,
			"remaining": remaining,
			"retry_after": 0,
			"reset_in": reset_in,
		}


sliding_window_limiter = RedisSlidingWindowLimiter(
	redis_client=redis_client,
	limit=settings.RATE_LIMIT_REQUESTS,
	window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)
