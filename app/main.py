from typing import Dict

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.limiter.redis_client import ping_redis

app = FastAPI(title="Distributed Rate Limiter POC")


@app.get("/")
def health() -> Dict[str, str]:
	# Simple health endpoint for quick checks and load balancer probes.
	return {"status": "running"}


@app.get("/health")
def redis_health() -> Dict[str, bool | str]:
	return {"status": "ok", "redis": ping_redis()}


app.include_router(api_router, prefix="/api")
