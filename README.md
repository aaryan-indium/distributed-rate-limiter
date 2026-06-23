# Distributed Rate Limiter POC

## Overview

This project demonstrates distributed rate limiting with FastAPI, Redis, Docker, Nginx, Prometheus, and Grafana. It implements three working algorithms: Fixed Window, Token Bucket, and Sliding Window. The app fails open when Redis is unavailable so test traffic is allowed instead of returning a server error.

## Architecture

```text
Client
  |
  v
Nginx:8000
  |
  +--> app1:8001
  |      |
  |      v
  |    Redis:6379
  |
  +--> app2:8002
         |
         v
       Redis:6379

Prometheus:9090 --> Grafana:3000
```

Nginx load-balances requests across two FastAPI app instances. Both app instances share Redis as the central rate-limit state store, while Prometheus scrapes per-endpoint metrics from `/metrics` and Grafana uses Prometheus as its default datasource.

## Algorithms Implemented

### Fixed Window

Fixed Window counts requests in a fixed time window using Redis `INCR` and `EXPIRE`. It is simple, fast, and easy to reason about, but can allow bursts around window boundaries. Use it when low complexity matters more than perfectly smooth traffic shaping.

### Token Bucket

Token Bucket stores `tokens` and `last_refill` in a Redis hash, refilling capacity over elapsed time and consuming one token per request. It supports controlled bursts and smoother recovery than Fixed Window, at the cost of more state and concurrency logic. Use it when clients should be able to burst briefly without exceeding a sustained average rate.

### Sliding Window

Sliding Window blends the previous window count with the current window count to reduce boundary spikes. It is smoother than Fixed Window and more consistent near clock boundaries, but its current implementation does not yet use WATCH/MULTI. Use it when boundary fairness is more important than the simplest possible implementation.

## Project Structure

```text
distributed-rate-limiter/
  .gitignore                         # Ignore Python, environment, editor, and generated files.
  conftest.py                        # Root pytest configuration helper.
  docker-compose.yml                 # Six-service stack: redis, app1, app2, nginx, prometheus, grafana.
  Dockerfile                         # FastAPI app image build recipe.
  README.md                          # Project overview and usage guide.
  requirements.txt                   # Python app and test dependencies.
  app/
    __init__.py                      # App package marker.
    main.py                          # FastAPI app, health endpoints, metrics, and API router registration.
    api/
      __init__.py                    # API package marker.
      routes.py                      # Test endpoints guarded by each limiter algorithm.
    config/
      __init__.py                    # Config package marker.
      settings.py                    # Environment-driven app settings.
    limiter/
      __init__.py                    # Limiter package marker.
      fixed_window.py                # Redis Fixed Window limiter.
      redis_client.py                # Shared Redis client and ping helper.
      sliding_window.py              # Redis Sliding Window limiter.
      token_bucket.py                # Redis Token Bucket limiter.
  docker/
    nginx.conf                       # Nginx upstream and proxy configuration.
  monitoring/
    prometheus.yml                   # Prometheus scrape config for app1 and app2.
    grafana/
      datasources.yml                # Grafana Prometheus datasource provisioning.
  tests/
    conftest.py                      # Mock Redis pytest fixture.
    test_rate_limiters.py            # 16 mocked unit tests for all three algorithms.
```

## How to Run

Prerequisites: Docker Desktop.

```bash
docker compose up --build
```

The stack exposes Nginx on `localhost:8000`, app1 on `localhost:8001`, app2 on `localhost:8002`, Redis on `localhost:6379`, Prometheus on `localhost:9090`, and Grafana on `localhost:3000`.

## How to Test Without Docker

```bash
python -m pytest tests/ -v
```

The current unit suite has 16 passing tests: 5 Fixed Window tests, 5 Token Bucket tests, and 6 Sliding Window tests. All limiter tests use mocked Redis clients, so they do not require a running Redis server.

## Endpoints

- `GET /` - basic app status.
- `GET /health` - app status plus Redis connectivity.
- `GET /metrics` - Prometheus metrics, auto-tracked per endpoint.
- `GET /api/test` - Fixed Window rate-limited test endpoint.
- `GET /api/test/token` - Token Bucket rate-limited test endpoint.
- `GET /api/test/sliding` - Sliding Window rate-limited test endpoint.

Rate-limited API endpoints require the `X-User-ID` header.

## Environment Variables

- `REDIS_URL` - Redis connection URL. Default: `redis://localhost:6379`.
- `RATE_LIMIT_REQUESTS` - Request limit or bucket capacity. Default: `10`.
- `RATE_LIMIT_WINDOW_SECONDS` - Window length and refill period in seconds. Default: `60`.

## Milestones

- [x] M1: FastAPI skeleton and Docker Compose setup.
- [x] M2: Redis integration and Fixed Window rate limiter.
- [x] M3: Token Bucket algorithm and unit tests.
- [x] M4: Sliding Window Counter.
- [x] M5: Prometheus and Grafana observability.

## Known Limitations

- Fixed Window uses separate `INCR` and `EXPIRE` calls, so there is a small atomicity gap if Redis fails between those operations.
- Sliding Window currently lacks WATCH/MULTI or Lua-based atomic updates, so concurrent requests can race.
- There is no circuit breaker yet; Redis failures are handled by fail-open route logic.
