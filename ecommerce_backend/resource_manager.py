"""
Resource Manager – Cached Thread Pool Controller
=========================================================
"""

import time
from threading import BoundedSemaphore, Lock
from django.conf import settings

from ecommerce_backend.metrics import (
    system_running_requests,
    system_waiting_requests,
    system_remaining_capacity,
    system_rejected_total,
)

MAX_WORKERS = getattr(settings, "SYSTEM_MAX_WORKERS", 20)
MAX_QUEUE_SIZE = getattr(settings, "SYSTEM_MAX_QUEUE_SIZE", 100)
IDLE_TIMEOUT = 10

class ResourceManager:
    """Simulates a Cached Thread Pool with a hard limit."""

    def __init__(self) -> None:
        self._total_capacity = MAX_WORKERS + MAX_QUEUE_SIZE
        
        # Outer gate – limits total admitted requests
        self._admission = BoundedSemaphore(self._total_capacity)
        
        # Inner gate – limits concurrently executing requests
        self._workers = BoundedSemaphore(MAX_WORKERS)

        self._lock = Lock()
        self._running = 0       # Currently busy
        self._waiting = 0       # In queue
        self._spawned = 1       # Currently "alive" threads
        self._rejected = 0
        self._last_active = time.time()
        
        self._sync_prometheus()

    def _sync_prometheus(self) -> None:
        system_running_requests.set(self._running)
        system_waiting_requests.set(self._waiting)
        system_remaining_capacity.set(
            self._total_capacity - self._running - self._waiting,
        )

    def acquire(self) -> bool:
        # 1. Admission Gate
        admitted = self._admission.acquire(blocking=False)
        if not admitted:
            with self._lock:
                self._rejected += 1
                system_rejected_total.inc()
            return False

        with self._lock:
            self._waiting += 1
            self._sync_prometheus()

        # 2. Worker Gate (Wait for a slot)
        self._workers.acquire(blocking=True)

        with self._lock:
            self._waiting -= 1
            self._running += 1
            
            # CACHED BEHAVIOR: Spawn a thread if we need one
            if self._running > self._spawned:
                self._spawned = self._running
                
            self._last_active = time.time()
            self._sync_prometheus()

        return True

    def release(self) -> None:
        self._workers.release()

        with self._lock:
            self._running -= 1
            self._last_active = time.time()
            self._sync_prometheus()

        self._admission.release()

    def get_metrics(self) -> dict:
        with self._lock:
            # Lazy decay of idle threads to eliminate background Timer threads
            now = time.time()
            if now - self._last_active >= IDLE_TIMEOUT:
                if self._spawned > self._running:
                    self._spawned = max(1, self._running)
            
            remaining_capacity = self._total_capacity - self._running - self._waiting
            return {
                "thread_pool": {
                    "type": "Cached",
                    "max_workers": MAX_WORKERS,
                    "spawned_threads": self._spawned,
                    "running_threads": self._running,
                    "idle_waiting_to_die": self._spawned - self._running,
                },
                "global_queue": {
                    "max_queue_size": MAX_QUEUE_SIZE,
                    "waiting_requests": self._waiting,
                    "remaining_queue_slots": MAX_QUEUE_SIZE - self._waiting,
                },
                "total_capacity": self._total_capacity,
                "total_in_system": self._running + self._waiting,
                "remaining_capacity": remaining_capacity,
                "rejected_total": self._rejected,
            }

resource_manager = ResourceManager()
