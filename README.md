# Distributed Rate Limiter POC

## Overview

This project demonstrates distributed rate limiting with FastAPI, Redis, Docker, and Nginx.

It currently includes:

- Distributed rate limiting using FastAPI + Redis
- Three algorithms: Fixed Window, Token Bucket, Sliding Window (in progress)
- Multi-instance deployment with an Nginx load balancer
- Centralized Redis state shared across all app instances
- A unit test suite that uses mocked Redis clients
- Observability with Prometheus + Grafana coming soon

## Architecture

```text
Client
	|
	v
Nginx :8000
	|
	+--> app1 :8001 -> Redis :6379
	|
	+--> app2 :8002 -> Redis :6379
```

Nginx forwards incoming traffic to either FastAPI instance. Both app instances read and write the same Redis state, which is what makes the limiter consistent across servers.

## Algorithms Implemented

### Fixed Window Counter

Implemented with Redis `INCR` + `EXPIRE`.

Tradeoff: simple and fast, but it can allow bursts around window boundaries.

### Token Bucket

Implemented with a Redis hash that stores `tokens` and `last_refill`.

Tradeoff: better burst handling and smoother refill behavior, but the logic is more complex than fixed window.

### Sliding Window Counter

In progress.

Tradeoff: typically smoother than fixed window and more precise near boundaries, but not implemented yet in this POC.

## Project Structure

```text
distributed-rate-limiter/
├── app/
│   ├── __init__.py            # App package marker.
│   ├── main.py                # FastAPI app, / and /health endpoints, router registration.
│   ├── api/
│   │   ├── __init__.py        # API package marker.
│   │   └── routes.py          # /api/test route and request-level rate limiting.
│   ├── config/
│   │   ├── __init__.py        # Config package marker.
│   │   └── settings.py        # BaseSettings configuration and defaults.
│   └── limiter/
│       ├── __init__.py        # Limiter package marker.
│       ├── redis_client.py    # Shared Redis client and ping helper.
│       ├── fixed_window.py    # RedisFixedWindowRateLimiter implementation.
│       └── token_bucket.py    # RedisTokenBucketLimiter implementation.
├── tests/
│   ├── conftest.py            # pytest fixture for mocked Redis.
│   └── test_rate_limiters.py  # Unit tests for fixed window and token bucket.
├── docker/
│   └── nginx.conf             # Nginx upstream and proxy configuration.
├── docker-compose.yml         # Redis, app1, app2, and Nginx service definitions.
├── Dockerfile/                # Container build context used by the current compose file.
├── Dockerfile.new             # Temporary copy of the app image recipe.
├── requirements.txt           # Python dependencies for app and tests.
└── README.md                  # Project overview and usage guide.
```

## How to Run

Prerequisites: Docker Desktop

```bash
docker compose up --build
curl localhost:8000/health
curl -H "X-User-ID: user123" localhost:8000/api/test
```

## How to Test (without Docker)

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Environment Variables

- `REDIS_URL` - default: `redis://localhost:6379`
- `RATE_LIMIT_REQUESTS` - default: `10`
- `RATE_LIMIT_WINDOW_SECONDS` - default: `60`

## Milestones

- ✅ M1: FastAPI skeleton + Docker Compose setup
- ✅ M2: Redis integration + Fixed Window rate limiter
- ✅ M3: Token Bucket algorithm + unit tests
- ⬜ M4: Sliding Window Counter
- ⬜ M5: Prometheus + Grafana observability
