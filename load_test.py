from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict


ENDPOINTS = {
    "fixed_window": "/api/test",
    "token_bucket": "/api/test/token",
    "sliding_window": "/api/test/sliding",
}

THREADS_PER_ENDPOINT = 10
REQUESTS_PER_THREAD = 15
REQUEST_TIMEOUT_SECONDS = 5


@dataclass
class EndpointStats:
    sent: int = 0
    allowed: int = 0
    rejected: int = 0
    errors: int = 0
    status_counts: Dict[int, int] = field(default_factory=dict)

    def record_status(self, status_code: int) -> None:
        self.sent += 1
        self.status_counts[status_code] = self.status_counts.get(status_code, 0) + 1
        if status_code == 200:
            self.allowed += 1
        elif status_code == 429:
            self.rejected += 1
        else:
            self.errors += 1

    def record_error(self) -> None:
        self.sent += 1
        self.errors += 1


def build_url(base_url: str, endpoint: str) -> str:
    return base_url.rstrip("/") + endpoint


def send_request(base_url: str, endpoint: str, user_id: str) -> int | None:
    request = urllib.request.Request(
        build_url(base_url, endpoint),
        headers={"X-User-ID": user_id},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return None


def worker(base_url: str, endpoint_name: str, endpoint_path: str, thread_id: int, start_gate: threading.Barrier, stats: EndpointStats) -> None:
    try:
        start_gate.wait()
    except threading.BrokenBarrierError:
        return

    user_id = f"loadtest-{thread_id}"
    for _ in range(REQUESTS_PER_THREAD):
        status_code = send_request(base_url, endpoint_path, user_id)
        if status_code is None:
            stats.record_error()
        else:
            stats.record_status(status_code)


def run_load_test(base_url: str) -> dict[str, EndpointStats]:
    stats_by_endpoint = {name: EndpointStats() for name in ENDPOINTS}
    start_gate = threading.Barrier(THREADS_PER_ENDPOINT * len(ENDPOINTS) + 1)
    threads: list[threading.Thread] = []

    for endpoint_name, endpoint_path in ENDPOINTS.items():
        for thread_index in range(THREADS_PER_ENDPOINT):
            thread = threading.Thread(
                target=worker,
                args=(base_url, endpoint_name, endpoint_path, thread_index, start_gate, stats_by_endpoint[endpoint_name]),
                daemon=False,
            )
            threads.append(thread)
            thread.start()

    try:
        start_gate.wait()
    except threading.BrokenBarrierError:
        pass

    for thread in threads:
        thread.join()

    return stats_by_endpoint


def print_summary(stats_by_endpoint: dict[str, EndpointStats]) -> None:
    headers = ("Endpoint", "Sent", "200", "429", "Errors")
    rows = []
    totals = EndpointStats()

    for endpoint_name, stats in stats_by_endpoint.items():
        totals.sent += stats.sent
        totals.allowed += stats.allowed
        totals.rejected += stats.rejected
        totals.errors += stats.errors
        rows.append(
            (
                endpoint_name,
                str(stats.sent),
                str(stats.allowed),
                str(stats.rejected),
                str(stats.errors),
            )
        )

    rows.append(
        (
            "total",
            str(totals.sent),
            str(totals.allowed),
            str(totals.rejected),
            str(totals.errors),
        )
    )

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(values: tuple[str, str, str, str, str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    separator = "-+-".join("-" * width for width in widths)

    print("\nLoad Test Summary")
    print(format_row(headers))
    print(separator)
    for row in rows:
        print(format_row(row))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a threaded load test against the rate limiter API.")
    parser.add_argument(
        "base_url",
        nargs="?",
        default="http://localhost:8000",
        help="Base URL of the app or Docker ingress, default: http://localhost:8000",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stats = run_load_test(args.base_url)
    print_summary(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
