"""
stress_test_resources – Prove the Resource Manager works
=========================================================

Usage (while the dev server is running on another terminal):

    python manage.py stress_test_resources

This command fires concurrent HTTP requests at the server and shows:
  1. Requests within capacity succeed (some may queue and wait).
  2. Requests beyond total capacity (workers + queue) are rejected.
  3. The /system/metrics endpoint shows running vs waiting counts.
  4. After the burst, the system recovers normally.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter

from django.conf import settings
from django.core.management.base import BaseCommand


BASE_URL = "http://127.0.0.1:8080"
PRODUCTS_URL = f"{BASE_URL}/products?limit=1"
METRICS_URL = f"{BASE_URL}/system/metrics"

MAX_WORKERS = getattr(settings, "SYSTEM_MAX_WORKERS", 5)
MAX_QUEUE = getattr(settings, "SYSTEM_MAX_QUEUE_SIZE", 20)
TOTAL_CAPACITY = MAX_WORKERS + MAX_QUEUE

# Create a session with a high connection pool size to allow massive concurrency and Keep-Alive connection reuse
session = requests.Session()
adapter = HTTPAdapter(pool_connections=2000, pool_maxsize=2000)
session.mount('http://', adapter)
session.mount('https://', adapter)


def fetch(url: str, timeout: float = 30) -> tuple[int, float]:
    """Return (HTTP status code, elapsed seconds)."""
    start = time.perf_counter()
    try:
        resp = session.get(url, timeout=timeout)
        # Consume the content to keep the connection alive in the pool
        _ = resp.content
        return resp.status_code, time.perf_counter() - start
    except Exception:
        # Catch connection refused, timeouts, etc.
        return 0, time.perf_counter() - start


def fetch_metrics() -> dict | None:
    try:
        resp = session.get(METRICS_URL, timeout=5)
        return resp.json()
    except Exception:
        return None


class Command(BaseCommand):
    help = "Fire concurrent requests to demonstrate the Resource Manager queue + worker pool."

    def add_arguments(self, parser):
        parser.add_argument(
            "--duration",
            type=int,
            default=0,
            help="Duration of the test in seconds (0 for burst mode).",
        )
        parser.add_argument(
            "--burst",
            type=int,
            default=TOTAL_CAPACITY + 50,
            help="Number of requests to fire in each burst.",
        )

    def handle(self, *args, **options):
        duration = options["duration"]
        burst_size = options["burst"]

        if duration > 0:
            self._sustained_load(duration, burst_size)
            return
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n══════════════════════════════════════════════════"
        ))
        self.stdout.write(self.style.MIGRATE_HEADING(
            "   Resource Manager – Queue + Worker Pool Test"
        ))
        self.stdout.write(self.style.MIGRATE_HEADING(
            "══════════════════════════════════════════════════\n"
        ))

        self.stdout.write(
            f"  Configuration:\n"
            f"    SYSTEM_MAX_WORKERS    = {MAX_WORKERS}  (concurrent execution)\n"
            f"    SYSTEM_MAX_QUEUE_SIZE = {MAX_QUEUE}  (waiting slots)\n"
            f"    Total capacity        = {TOTAL_CAPACITY}  (workers + queue)\n"
        )

        # ── Step 1: Verify baseline ──────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n── Step 1: Baseline – single request ──"
        ))
        code, elapsed = fetch(PRODUCTS_URL)
        if code == 200:
            self.stdout.write(self.style.SUCCESS(
                f"  ✔ Single request returned HTTP {code} in {elapsed:.3f}s"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"  ✘ Unexpected HTTP {code} – is the server running?"
            ))
            return

        # ── Step 2: Burst within capacity (should all succeed) ───────
        burst_count = TOTAL_CAPACITY
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n── Step 2: Burst {burst_count} requests "
            f"(within capacity – all should succeed, some may queue) ──"
        ))
        results, times = self._fire_burst(burst_count)
        ok = results.get(200, 0)
        rejected = results.get(503, 0)
        self.stdout.write(
            f"  HTTP 200 (OK):       {ok}\n"
            f"  HTTP 503 (rejected): {rejected}\n"
            f"  Avg response time:   {sum(times)/len(times):.3f}s\n"
            f"  Max response time:   {max(times):.3f}s  "
            f"(high = requests waited in queue)"
        )
        if ok == burst_count:
            self.stdout.write(self.style.SUCCESS(
                f"  ✔ All {burst_count} requests succeeded – "
                f"queue absorbed the burst!"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  ⚠ {rejected} requests were rejected. "
                f"The burst may have exceeded queue capacity."
            ))

        # ── Step 3: Burst OVER capacity ──────────────────────────────
        over_count = TOTAL_CAPACITY + 30
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n── Step 3: Burst {over_count} requests "
            f"(OVER capacity – some should be rejected) ──"
        ))
        results, times = self._fire_burst(over_count)
        ok = results.get(200, 0)
        rejected = results.get(503, 0)
        self.stdout.write(
            f"  HTTP 200 (OK):       {ok}\n"
            f"  HTTP 503 (rejected): {rejected}"
        )
        if rejected > 0:
            self.stdout.write(self.style.SUCCESS(
                f"  ✔ {rejected} requests correctly rejected – "
                f"queue was full, system protected!"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "  ⚠ No requests were rejected – the burst "
                "may not have saturated the queue."
            ))

        # ── Step 4: Recovery ─────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n── Step 4: Recovery – request after burst ──"
        ))
        time.sleep(1)
        code, elapsed = fetch(PRODUCTS_URL)
        if code == 200:
            self.stdout.write(self.style.SUCCESS(
                f"  ✔ Post-burst request returned HTTP {code} "
                f"in {elapsed:.3f}s – system recovered"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"  ✘ Post-burst request returned HTTP {code}"
            ))

        # ── Step 5: Show metrics ─────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n── Step 5: Resource Manager metrics ──"
        ))
        metrics = fetch_metrics()
        if metrics:
            for key, val in metrics.items():
                self.stdout.write(f"  {key}: {val}")
        else:
            self.stdout.write(self.style.ERROR(
                "  Could not fetch metrics"
            ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n══════════════════════════════════════════════════\n"
        ))

    def _sustained_load(self, duration: int, burst_size: int):
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n🚀 Starting SUSTAINED LOAD for {duration} seconds (Burst size: {burst_size})\n"
        ))
        
        start_time = time.time()
        total_ok = 0
        total_rejected = 0
        iteration = 0
        
        while time.time() - start_time < duration:
            iteration += 1
            results, times = self._fire_burst(burst_size)
            ok = results.get(200, 0)
            rejected = results.get(503, 0)
            total_ok += ok
            total_rejected += rejected
            
            avg = sum(times)/len(times) if times else 0
            self.stdout.write(
                f"Iteration {iteration}: OK={ok}, Rejected={rejected}, Avg={avg:.3f}s"
            )
            time.sleep(0.1) # Small pause between bursts
            
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Finished Sustained Load\n"
            f"Total OK:       {total_ok}\n"
            f"Total Rejected: {total_rejected}\n"
            f"Total Requests: {total_ok + total_rejected}"
        ))

    def _fire_burst(self, count: int) -> tuple[dict[int, int], list[float]]:
        """Fire `count` concurrent GET requests.

        Returns (status_code_counts, list_of_elapsed_times).
        """
        results: dict[int, int] = {}
        times: list[float] = []

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [
                pool.submit(fetch, PRODUCTS_URL) for _ in range(count)
            ]
            for future in as_completed(futures):
                code, elapsed = future.result()
                results[code] = results.get(code, 0) + 1
                times.append(elapsed)

        return results, times
