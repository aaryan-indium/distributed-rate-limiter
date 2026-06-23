import redis

from app.config.settings import settings


def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


redis_client = get_redis_client()


def ping_redis() -> bool:
    try:
        return bool(redis_client.ping())
    except Exception:
        return False