from prometheus_client import Gauge, Counter, Histogram

checkout_running_tasks = Gauge(
    "checkout_running_tasks",
    "Number of checkout tasks currently running"
)

checkout_waiting_tasks = Gauge(
    "checkout_waiting_tasks",
    "Number of checkout tasks waiting in queue"
)

checkout_remaining_capacity = Gauge(
    "checkout_remaining_capacity",
    "Remaining checkout queue capacity"
)

checkout_rejected_total = Counter(
    "checkout_rejected_total",
    "Total checkout tasks rejected because queue is full"
)

checkout_completed_total = Counter(
    "checkout_completed_total",
    "Total checkout tasks completed"
)

checkout_failed_total = Counter(
    "checkout_failed_total",
    "Total checkout tasks failed"
)

checkout_duration_seconds = Histogram(
    "checkout_duration_seconds",
    "Checkout processing duration in seconds"
)

# ---------------------------------------------------------------------------
# System-wide resource-manager metrics
# ---------------------------------------------------------------------------

system_running_requests = Gauge(
    "system_running_requests",
    "Number of requests currently being executed by worker threads"
)

system_waiting_requests = Gauge(
    "system_waiting_requests",
    "Number of requests waiting in the queue for a worker thread"
)

system_remaining_capacity = Gauge(
    "system_remaining_capacity",
    "Remaining queue capacity before the system starts rejecting requests"
)

system_rejected_total = Counter(
    "system_rejected_total",
    "Total requests rejected because the queue reached maximum capacity"
)
