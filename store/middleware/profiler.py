import time
import logging
import os
from django.db import connection
from django.conf import settings

logger = logging.getLogger(__name__)

LOG_FILE = os.path.join(settings.BASE_DIR, 'logs', 'request_timings.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

class SafeTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        
        
        
        
        response = self.get_response(request)
        
        duration = time.time() - start_time
        queue_time = getattr(request, 'queue_time', 0.0)
        
        db_queries = len(connection.queries)
        db_time = sum(float(q.get('time', 0)) for q in connection.queries) if db_queries > 0 else 0
        
        
        if duration > 1.0 or queue_time > 1.0 or response.status_code >= 400:
            log_line = f"[{time.strftime('%H:%M:%S')}] {request.method} {request.path} | Status: {response.status_code} | Total Time: {duration:.4f}s | Queue Wait: {queue_time:.4f}s | DB Queries: {db_queries} | DB Time: {db_time:.4f}s\n"
            
            try:
                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(log_line)
            except Exception:
                pass

        return response
