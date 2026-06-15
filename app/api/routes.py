"""API routes for the rate limiter POC."""

from typing import Dict

from fastapi import APIRouter, HTTPException, Request, status

from app.config.settings import settings
from app.limiter.fixed_window import RedisFixedWindowRateLimiter
from app.limiter.redis_client import redis_client
from app.limiter.sliding_window import sliding_window_limiter
from app.limiter.token_bucket import token_bucket_limiter

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

    try:
        result = limiter.allow_request(user_id)
    except Exception:
        return {
            "ok": True,
            "user_id": user_id,
            "remaining": -1,
            "reset_in_seconds": -1,
            "warning": "rate limiter unavailable, request allowed",
        }

    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result['retry_after']}s.",
            headers={"Retry-After": str(result["retry_after"])},
        )

    return {
        "ok": True,
        "algorithm": "fixed_window",
        "user_id": user_id,
        "remaining": result["remaining"],
        "reset_in_seconds": result["reset_in"],
    }


@router.get("/test/token")
def test_token_bucket(request: Request) -> Dict[str, object]:
    """Test endpoint guarded by the token bucket limiter."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header is required",
        )

    try:
        result = token_bucket_limiter.allow_request(user_id)
    except Exception:
        return {
            "ok": True,
            "user_id": user_id,
            "remaining": -1,
            "reset_in_seconds": -1,
            "warning": "rate limiter unavailable, request allowed",
        }

    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result['retry_after']}s.",
            headers={"Retry-After": str(result["retry_after"])},
        )

    return {
        "ok": True,
        "algorithm": "token_bucket",
        "user_id": user_id,
        "remaining": result["remaining"],
        "reset_in_seconds": result["reset_in"],
    }


@router.get("/test/sliding")
def test_sliding_window(request: Request) -> Dict[str, object]:
    """Test endpoint guarded by the sliding window limiter."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="X-User-ID header is required",
        )

    try:
        result = sliding_window_limiter.allow_request(user_id)
    except Exception:
        return {
            "ok": True,
            "user_id": user_id,
            "remaining": -1,
            "reset_in_seconds": -1,
            "warning": "rate limiter unavailable, request allowed",
        }

    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {result['retry_after']}s.",
            headers={"Retry-After": str(result["retry_after"])},
        )

    return {
        "ok": True,
        "algorithm": "sliding_window",
        "user_id": user_id,
        "remaining": result["remaining"],
        "reset_in_seconds": result["reset_in"],
    }
