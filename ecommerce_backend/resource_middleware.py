"""
Resource Manager Middleware
===========================

Django middleware that wraps every incoming request with the
ResourceManager's semaphore.  This ensures the server never processes
more than ``SYSTEM_MAX_WORKERS + SYSTEM_MAX_QUEUE_SIZE`` requests at
the same time.

If all slots are occupied the middleware short-circuits and returns
HTTP 503 (Service Unavailable) without hitting the view layer at all.
"""

import logging
import time

from django.http import JsonResponse

from ecommerce_backend.resource_manager import resource_manager

logger = logging.getLogger("resource_manager")


OBSERVABILITY_PATHS = {
    "/metrics",
    "/system/local-metrics",
    "/system/metrics",
    "/system/dashboard",
}


class ResourceManagerMiddleware:
    """Limit the number of concurrent requests processed by the server."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in OBSERVABILITY_PATHS:
            return self.get_response(request)

        # ---- try to acquire a processing slot ----
        if not resource_manager.acquire():
            logger.warning(
                "Request rejected – system at capacity  path=%s",
                request.path,
            )
            return JsonResponse(
                {
                    "error": "Queue is full. All workers are busy and no "
                             "waiting slots are available. "
                             "Please try again shortly.",
                },
                status=503,
            )

        start = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            resource_manager.release()
            elapsed = time.perf_counter() - start
            logger.debug(
                "Request completed  path=%s  elapsed=%.3fs",
                request.path,
                elapsed,
            )

        return response
