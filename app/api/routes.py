"""API routes for the rate limiter POC."""

from typing import Dict

from fastapi import APIRouter, HTTPException, Request, status

from app.config.settings import settings
from app.limiter.fixed_window import RedisFixedWindowRateLimiter
from app.limiter.redis_client import redis_client

router = APIRouter()

limiter = RedisFixedWindowRateLimiter(
    redis_client=redis_client,
    limit=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)


@router.get("/test")
def test_rate_limit(request: Request) -> Dict[str, object]:
    """Test endpoint guarded by the fixed window limiter."""
    # Request flow:
    # 1. Read the user identifier from X-User-ID.
    # 2. Ask the limiter if this request is allowed.
    # 3. If blocked, return 429 with a helpful message.
    # 4. If allowed, return success with remaining quota info.
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header is required",
        )

    result = limiter.allow_request(user_id)

    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result['retry_after']}s.",
            headers={"Retry-After": str(result["retry_after"])},
        )

    return {
        "ok": True,
        "user_id": user_id,
        "remaining": result["remaining"],
        "reset_in_seconds": result["reset_in"],
    }
