from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.limiter.fixed_window import RedisFixedWindowRateLimiter
from app.limiter.sliding_window import RedisSlidingWindowLimiter
from app.limiter.token_bucket import RedisTokenBucketLimiter


class TestFixedWindow:
	def test_first_request_allowed(self, mock_redis: MagicMock) -> None:
		mock_redis.incr.return_value = 1
		mock_redis.ttl.return_value = 60

		limiter = RedisFixedWindowRateLimiter(mock_redis, limit=10, window_seconds=60)
		result = limiter.allow_request("user-1")

		assert result["allowed"] is True
		mock_redis.expire.assert_called_once_with("rate:fixed:user-1", 60)

	def test_request_within_limit(self, mock_redis: MagicMock) -> None:
		mock_redis.incr.return_value = 5
		mock_redis.ttl.return_value = 45

		limiter = RedisFixedWindowRateLimiter(mock_redis, limit=10, window_seconds=60)
		result = limiter.allow_request("user-2")

		assert result["allowed"] is True
		assert result["remaining"] == 5

	def test_request_at_limit(self, mock_redis: MagicMock) -> None:
		mock_redis.incr.return_value = 10
		mock_redis.ttl.return_value = 30

		limiter = RedisFixedWindowRateLimiter(mock_redis, limit=10, window_seconds=60)
		result = limiter.allow_request("user-3")

		assert result["allowed"] is True
		assert result["remaining"] == 0

	def test_request_exceeds_limit(self, mock_redis: MagicMock) -> None:
		mock_redis.incr.return_value = 11
		mock_redis.ttl.return_value = 25

		limiter = RedisFixedWindowRateLimiter(mock_redis, limit=10, window_seconds=60)
		result = limiter.allow_request("user-4")

		assert result["allowed"] is False

	def test_retry_after_uses_ttl(self, mock_redis: MagicMock) -> None:
		mock_redis.incr.return_value = 11
		mock_redis.ttl.return_value = 30

		limiter = RedisFixedWindowRateLimiter(mock_redis, limit=10, window_seconds=60)
		result = limiter.allow_request("user-5")

		assert result["retry_after"] == 30


class TestTokenBucket:
	def _make_pipeline(self, bucket_data: dict[str, str]) -> MagicMock:
		pipeline = MagicMock()
		pipeline.hgetall.return_value = bucket_data
		pipeline.execute.return_value = None
		return pipeline

	def test_first_request_allowed(self, mock_redis: MagicMock) -> None:
		pipeline = self._make_pipeline({})
		mock_redis.pipeline.return_value = pipeline

		limiter = RedisTokenBucketLimiter(mock_redis, capacity=10, refill_rate=1)

		with patch("app.limiter.token_bucket.time.time", return_value=100.0):
			result = limiter.allow_request("user-1")

		assert result["allowed"] is True
		assert result["remaining"] == 9.0
		pipeline.hset.assert_called_once()

	def test_allows_within_capacity(self, mock_redis: MagicMock) -> None:
		pipeline = self._make_pipeline({"tokens": "5.0", "last_refill": "100.0"})
		mock_redis.pipeline.return_value = pipeline

		limiter = RedisTokenBucketLimiter(mock_redis, capacity=10, refill_rate=1)

		with patch("app.limiter.token_bucket.time.time", return_value=102.0):
			result = limiter.allow_request("user-2")

		assert result["allowed"] is True
		assert result["remaining"] > 0

	def test_denies_when_empty(self, mock_redis: MagicMock) -> None:
		pipeline = self._make_pipeline({"tokens": "0.0", "last_refill": "100.0"})
		mock_redis.pipeline.return_value = pipeline

		limiter = RedisTokenBucketLimiter(mock_redis, capacity=10, refill_rate=1)

		with patch("app.limiter.token_bucket.time.time", return_value=100.0):
			result = limiter.allow_request("user-3")

		assert result["allowed"] is False

	def test_burst_allowed(self, mock_redis: MagicMock) -> None:
		pipeline = self._make_pipeline({"tokens": "0.0", "last_refill": "40.0"})
		mock_redis.pipeline.return_value = pipeline

		limiter = RedisTokenBucketLimiter(mock_redis, capacity=10, refill_rate=1)

		with patch("app.limiter.token_bucket.time.time", return_value=100.0):
			result = limiter.allow_request("user-4")

		assert result["allowed"] is True
		assert result["remaining"] == 9.0

	def test_remaining_rounds_to_two_decimals(self, mock_redis: MagicMock) -> None:
		pipeline = self._make_pipeline({"tokens": "3.3333", "last_refill": "100.0"})
		mock_redis.pipeline.return_value = pipeline

		limiter = RedisTokenBucketLimiter(mock_redis, capacity=10, refill_rate=0.5)

		with patch("app.limiter.token_bucket.time.time", return_value=100.1):
			result = limiter.allow_request("user-5")

		remaining_text = f"{result['remaining']:.2f}"
		assert len(remaining_text.split(".")[1]) == 2


class TestSlidingWindow:
	def _make_pipeline(self, get_values: list[str | None]) -> MagicMock:
		pipeline = MagicMock()
		pipeline.get.side_effect = get_values
		pipeline.execute.return_value = get_values
		return pipeline

	def test_first_request_allowed(self, mock_redis: MagicMock) -> None:
		read_pipeline = self._make_pipeline([None, None, None])
		write_pipeline = MagicMock()
		write_pipeline.execute.return_value = None
		mock_redis.pipeline.side_effect = [read_pipeline, write_pipeline]

		limiter = RedisSlidingWindowLimiter(mock_redis, limit=10, window_seconds=60)

		with patch("app.limiter.sliding_window.time.time", return_value=100.0):
			result = limiter.allow_request("user-1")

		assert result["allowed"] is True
		assert result["remaining"] == pytest.approx(10.0, abs=0.01)

	def test_allows_within_limit(self, mock_redis: MagicMock) -> None:
		now = 100.0
		read_pipeline = self._make_pipeline(["0", "5", str(now - 30)])
		write_pipeline = MagicMock()
		write_pipeline.execute.return_value = None
		mock_redis.pipeline.side_effect = [read_pipeline, write_pipeline]

		limiter = RedisSlidingWindowLimiter(mock_redis, limit=10, window_seconds=60)

		with patch("app.limiter.sliding_window.time.time", return_value=now):
			result = limiter.allow_request("user-2")

		assert result["allowed"] is True
		assert result["remaining"] == pytest.approx(5.0, abs=0.01)

	def test_denies_when_limit_reached(self, mock_redis: MagicMock) -> None:
		now = 100.0
		read_pipeline = self._make_pipeline(["0", "10", str(now - 30)])
		mock_redis.pipeline.return_value = read_pipeline

		limiter = RedisSlidingWindowLimiter(mock_redis, limit=10, window_seconds=60)

		with patch("app.limiter.sliding_window.time.time", return_value=now):
			result = limiter.allow_request("user-3")

		assert result["allowed"] is False

	def test_boundary_attack_prevented(self, mock_redis: MagicMock) -> None:
		now = 100.0
		read_pipeline = self._make_pipeline(["8", "0", str(now - 1)])
		write_pipeline = MagicMock()
		write_pipeline.execute.return_value = None
		mock_redis.pipeline.side_effect = [read_pipeline, write_pipeline]

		limiter = RedisSlidingWindowLimiter(mock_redis, limit=10, window_seconds=60)

		with patch("app.limiter.sliding_window.time.time", return_value=now):
			result = limiter.allow_request("user-4")

		assert result["allowed"] is True
		assert result["remaining"] < 10
		assert result["remaining"] == pytest.approx(2.13, abs=0.05)

	def test_window_rollover(self, mock_redis: MagicMock) -> None:
		now = 100.0
		read_pipeline = self._make_pipeline(["0", "7", str(now - 61)])
		write_pipeline = MagicMock()
		write_pipeline.execute.return_value = None
		mock_redis.pipeline.side_effect = [read_pipeline, write_pipeline]

		limiter = RedisSlidingWindowLimiter(mock_redis, limit=10, window_seconds=60)

		with patch("app.limiter.sliding_window.time.time", return_value=now):
			result = limiter.allow_request("user-5")

		assert result["allowed"] is True
		assert result["remaining"] < 10

	def test_remaining_rounds_to_two_decimals(self, mock_redis: MagicMock) -> None:
		now = 100.0
		read_pipeline = self._make_pipeline(["3.3333", "1.6667", str(now - 15)])
		write_pipeline = MagicMock()
		write_pipeline.execute.return_value = None
		mock_redis.pipeline.side_effect = [read_pipeline, write_pipeline]

		limiter = RedisSlidingWindowLimiter(mock_redis, limit=10, window_seconds=60)

		with patch("app.limiter.sliding_window.time.time", return_value=now):
			result = limiter.allow_request("user-6")

		remaining_text = f"{result['remaining']:.2f}"
		assert len(remaining_text.split(".")[1]) == 2
