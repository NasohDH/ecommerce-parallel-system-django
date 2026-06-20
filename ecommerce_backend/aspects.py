import logging
import time
from functools import wraps
from django.conf import settings
from django.http import JsonResponse

from ecommerce_backend.resource_manager import resource_manager

logger = logging.getLogger("aspects")

# --- SERVER RESOURCE ASPECT ---

OBSERVABILITY_PATHS = {
    "/metrics",
    "/system/local-metrics",
    "/system/metrics",
    "/system/dashboard",
}

class ServerResourceAspectMiddleware:
    """Aspect for tracking Server Resources (Thread Pool, Queue)"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "ENABLE_SERVER_TRACKING_ASPECT", True):
            return self.get_response(request)

        if request.path in OBSERVABILITY_PATHS:
            return self.get_response(request)

        if not resource_manager.acquire():
            logger.warning("Request rejected – system at capacity  path=%s", request.path)
            return JsonResponse({
                "error": "Queue is full. All workers are busy and no "
                         "waiting slots are available. "
                         "Please try again shortly."
            }, status=503)

        start = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            resource_manager.release()
            elapsed = time.perf_counter() - start
            logger.debug("Request completed  path=%s  elapsed=%.3fs", request.path, elapsed)

        return response

# --- NGINX TRACKING ASPECT ---

# In-memory store for requests per server
NGINX_REQUEST_COUNTS = {}

class NginxTrackingAspectMiddleware:
    """Aspect for tracking requests routed by Nginx"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "ENABLE_NGINX_TRACKING_ASPECT", True):
            return self.get_response(request)
            
        # Track Nginx Proxy Latency if X-Request-Start header is present
        # Nginx passes it as msec: e.g. 1718545892.123
        req_start = request.headers.get("X-Request-Start")
        if req_start:
            try:
                nginx_time = float(req_start)
                latency = time.time() - nginx_time
                logger.info("Nginx Tracking Aspect: Routing latency: %.3f seconds", latency)
            except ValueError:
                pass

        # Track requests per server port
        server_port = request.META.get('SERVER_PORT', 'Unknown')
        NGINX_REQUEST_COUNTS[server_port] = NGINX_REQUEST_COUNTS.get(server_port, 0) + 1
        
        logger.info(f"Nginx Tracking Aspect: Request processed on server port {server_port}. Total requests for this server: {NGINX_REQUEST_COUNTS[server_port]}")

        return self.get_response(request)

# --- REDIS TRACKING ASPECT ---

def redis_tracking_aspect(func):
    """Aspect decorator for tracking Redis calls"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not getattr(settings, "ENABLE_REDIS_TRACKING_ASPECT", True):
            return func(*args, **kwargs)
            
        start = time.perf_counter()
        
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        
        logger.info(f"Redis Tracking Aspect: Executed {func.__name__} in {elapsed:.4f} seconds")
        return result
    return wrapper
