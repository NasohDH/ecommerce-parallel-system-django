from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from uuid import uuid4

from django.db import close_old_connections
from rest_framework.exceptions import APIException

from ecommerce_backend.metrics import (
    checkout_completed_total,
    checkout_failed_total,
    checkout_rejected_total,
    checkout_remaining_capacity,
    checkout_running_tasks,
    checkout_waiting_tasks,
)
from store.models import Order
from store.services.errors import ServiceUnavailable
from store.services.order.order_checkout import checkout_cart


MAX_CHECKOUT_QUEUE_SIZE = 50


class CheckoutJob:
    def __init__(self, user_id: int) -> None:
        self.id = uuid4().hex
        self.user_id = user_id
        self.done = Event()
        self.result: Order | None = None
        self.error: Exception | None = None


class CheckoutQueue:
    def __init__(self, maxsize: int = MAX_CHECKOUT_QUEUE_SIZE) -> None:
        self._queue: Queue[str] = Queue(maxsize=maxsize)
        self._jobs: dict[str, CheckoutJob] = {}
        self._lock = Lock()
        self._stop_event = Event()
        self._worker: Thread | None = None
        self._enqueued_total = 0
        self._running_tasks = 0
        self._completed_total = 0
        self._failed_total = 0
        self._rejected_total = 0
        self._sync_prometheus()

    def _sync_prometheus(self) -> None:
        checkout_waiting_tasks.set(self._queue.qsize())
        checkout_running_tasks.set(self._running_tasks)
        checkout_remaining_capacity.set(self._queue.maxsize - self._queue.qsize())

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = Thread(
            target=self._run,
            name="checkout-queue-worker",
            daemon=True,
        )
        self._worker.start()

    def checkout(self, user_id: int) -> Order:
        job = self._enqueue(user_id)
        job.done.wait()
        if job.error:
            raise job.error
        if not job.result:
            raise APIException("Checkout finished without an order result.")
        return job.result

    def _enqueue(self, user_id: int) -> CheckoutJob:
        self.start()
        job = CheckoutJob(user_id=user_id)
        with self._lock:
            self._jobs[job.id] = job

        try:
            self._queue.put_nowait(job.id)
        except Full as exc:
            with self._lock:
                self._jobs.pop(job.id, None)
                self._rejected_total += 1
                checkout_rejected_total.inc()
                self._sync_prometheus()
            raise ServiceUnavailable(
                "Checkout queue is full. Please try again shortly."
            ) from exc

        with self._lock:
            self._enqueued_total += 1
            self._sync_prometheus()

        return job

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=1)
            except Empty:
                continue
            try:
                self._process(job_id)
            finally:
                self._queue.task_done()

    def _process(self, job_id: str) -> None:
        close_old_connections()
        with self._lock:
            job = self._jobs.get(job_id)

        if not job:
            return

        try:
            with self._lock:
                self._running_tasks += 1
                self._sync_prometheus()
            job.result = checkout_cart(job.user_id)
            with self._lock:
                self._completed_total += 1
                checkout_completed_total.inc()
        except Exception as exc:
            job.error = exc
            with self._lock:
                self._failed_total += 1
                checkout_failed_total.inc()
        finally:
            job.done.set()
            with self._lock:
                self._running_tasks -= 1
                self._jobs.pop(job_id, None)
                self._sync_prometheus()
            close_old_connections()

    def get_metrics(self) -> dict:
        with self._lock:
            waiting_tasks = self._queue.qsize()
            return {
                "max_queue_size": self._queue.maxsize,
                "waiting_tasks": waiting_tasks,
                "running_tasks": self._running_tasks,
                "remaining_capacity": self._queue.maxsize - waiting_tasks,
                "tracked_jobs": len(self._jobs),
                "enqueued_total": self._enqueued_total,
                "completed_total": self._completed_total,
                "failed_total": self._failed_total,
                "rejected_total": self._rejected_total,
                "worker_alive": bool(self._worker and self._worker.is_alive()),
            }


checkout_queue = CheckoutQueue()
