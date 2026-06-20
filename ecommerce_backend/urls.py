import json
import os
import socket
from urllib.error import URLError
from urllib.request import Request, urlopen
from threading import Lock
import psutil

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import include, path

from ecommerce_backend.resource_manager import resource_manager
from store.models import Order, DailySalesReport, DeadLetterSales

from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily

def _get_active_db_connections():
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SHOW STATUS LIKE 'Threads_connected';")
            row = cursor.fetchone()
            return int(row[1]) if row else 0
    except Exception:
        return 0

class WindowsProcessCollector:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent(interval=None)

    def collect(self):
        try:
            cpu_percent = self.process.cpu_percent(interval=None)
            g_cpu = GaugeMetricFamily("django_node_cpu_percent", "CPU utilization percentage of this Django node process")
            g_cpu.add_metric([], cpu_percent)
            yield g_cpu
        except Exception:
            pass
        try:
            memory_mb = self.process.memory_info().rss / (1024 * 1024)
            g_mem = GaugeMetricFamily("django_node_memory_mb", "Memory usage of this Django node process in MB")
            g_mem.add_metric([], memory_mb)
            yield g_mem
        except Exception:
            pass
        try:
            sys_cpu = psutil.cpu_percent(interval=None)
            g_sys_cpu = GaugeMetricFamily("system_cpu_percent", "Total system CPU utilization percentage")
            g_sys_cpu.add_metric([], sys_cpu)
            yield g_sys_cpu
        except Exception:
            pass
        try:
            sys_mem = psutil.virtual_memory().percent
            g_sys_mem = GaugeMetricFamily("system_memory_percent", "Total system memory utilization percentage")
            g_sys_mem.add_metric([], sys_mem)
            yield g_sys_mem
        except Exception:
            pass
        try:
            metrics = resource_manager.get_metrics()
            tp = metrics["thread_pool"]
            g_max_workers = GaugeMetricFamily("django_system_max_workers", "Max workers limit in the thread pool")
            g_max_workers.add_metric([], tp["max_workers"])
            yield g_max_workers
            g_spawned = GaugeMetricFamily("django_system_spawned_threads", "Total spawned threads currently alive")
            g_spawned.add_metric([], tp["spawned_threads"])
            yield g_spawned
            g_busy = GaugeMetricFamily("django_system_busy_threads", "Busy threads currently processing requests")
            g_busy.add_metric([], tp["running_threads"])
            yield g_busy
            g_idle = GaugeMetricFamily("django_system_idle_threads", "Idle threads waiting for work")
            g_idle.add_metric([], tp["idle_waiting_to_die"])
            yield g_idle
        except Exception:
            pass
        try:
            metrics = resource_manager.get_metrics()
            gq = metrics["global_queue"]
            g_max_q = GaugeMetricFamily("django_system_max_queue_size", "Max capacity of the global waiting queue")
            g_max_q.add_metric([], gq["max_queue_size"])
            yield g_max_q
            g_waiting = GaugeMetricFamily("django_system_waiting_requests", "Number of requests waiting in queue")
            g_waiting.add_metric([], gq["waiting_requests"])
            yield g_waiting
            g_rem_q = GaugeMetricFamily("django_system_remaining_queue_slots", "Remaining queue slots available")
            g_rem_q.add_metric([], gq["remaining_queue_slots"])
            yield g_rem_q
            g_rejected = GaugeMetricFamily("django_system_rejected_requests_total", "Total requests rejected due to full queue")
            g_rejected.add_metric([], metrics["rejected_total"])
            yield g_rejected
        except Exception:
            pass
        try:
            g_pending = GaugeMetricFamily("django_checkout_pending_orders", "Count of orders in pending status")
            g_pending.add_metric([], Order.objects.filter(status="pending").count())
            yield g_pending
            g_completed = GaugeMetricFamily("django_checkout_completed_orders", "Count of orders in completed status")
            g_completed.add_metric([], Order.objects.filter(status="completed").count())
            yield g_completed
            g_failed = GaugeMetricFamily("django_checkout_failed_orders", "Count of orders in failed status")
            g_failed.add_metric([], Order.objects.filter(status="failed").count())
            yield g_failed
        except Exception:
            pass
        try:
            latest_report = DailySalesReport.objects.order_by("-date").first()
            if latest_report:
                status_val = 0
                status_str = latest_report.status.lower()
                if "success" in status_str or "complete" in status_str:
                    status_val = 2
                elif "process" in status_str:
                    status_val = 1
                elif "fail" in status_str:
                    status_val = 3
                g_status = GaugeMetricFamily("django_daily_batch_status", "Status code of the latest daily sales batch")
                g_status.add_metric([], status_val)
                yield g_status
                g_batch_total = GaugeMetricFamily("django_daily_batch_total_orders", "Total orders in the latest daily batch")
                g_batch_total.add_metric([], latest_report.total_orders)
                yield g_batch_total
                g_batch_proc = GaugeMetricFamily("django_daily_batch_processed_orders", "Processed orders in the latest daily batch")
                g_batch_proc.add_metric([], latest_report.processed_orders)
                yield g_batch_proc
                g_batch_rev = GaugeMetricFamily("django_daily_batch_revenue", "Total revenue calculated in the latest daily batch")
                g_batch_rev.add_metric([], float(latest_report.total_revenue))
                yield g_batch_rev
                dead_letters = DeadLetterSales.objects.filter(report=latest_report).count()
                g_batch_dl = GaugeMetricFamily("django_daily_batch_dead_letters", "Failed sales records in the dead letter queue")
                g_batch_dl.add_metric([], dead_letters)
                yield g_batch_dl
        except Exception:
            pass
        try:
            g_db_conns = GaugeMetricFamily("django_db_active_connections", "Number of active database connections")
            g_db_conns.add_metric([], _get_active_db_connections())
            yield g_db_conns
        except Exception:
            pass
        try:
            cache_data = _get_cache_metrics()
            g_cache_hits = GaugeMetricFamily("django_redis_cache_hits", "Total cache hits")
            g_cache_hits.add_metric([], cache_data["hits"])
            yield g_cache_hits
            
            g_cache_misses = GaugeMetricFamily("django_redis_cache_misses", "Total cache misses")
            g_cache_misses.add_metric([], cache_data["misses"])
            yield g_cache_misses
            
            g_cache_ratio = GaugeMetricFamily("django_redis_cache_hit_ratio_percent", "Cache hit ratio percentage")
            g_cache_ratio.add_metric([], cache_data["hit_ratio_percent"])
            yield g_cache_ratio
        except Exception:
            pass

try:
    REGISTRY.register(WindowsProcessCollector())
except ValueError:
    pass


_GLOBAL_PROCESS = psutil.Process(os.getpid())
_GLOBAL_PROCESS.cpu_percent(interval=None)
psutil.cpu_percent(interval=None)
_METRICS_LOCK = Lock()


import time
_LAST_CPU_TIME = 0.0
_CACHED_CPU = 0.0
_LAST_SYSTEM_CPU_TIME = 0.0
_CACHED_SYSTEM_CPU = 0.0


_ASYNC_CHECKOUT_LOCK = Lock()
_LAST_ASYNC_CHECKOUT_FETCH = 0.0
_CACHED_PENDING = 0
_CACHED_COMPLETED = 0
_CACHED_FAILED = 0

_DAILY_BATCH_LOCK = Lock()
_LAST_DAILY_BATCH_FETCH = 0.0
_CACHED_DAILY_BATCH = None


def root_view(request):
    return JsonResponse({"message": "E-commerce API is running"})



def _local_metrics_payload(server_url=None, online=True, error=None, exclude_db=False):
    global _GLOBAL_PROCESS, _METRICS_LOCK, _LAST_CPU_TIME, _CACHED_CPU, _LAST_SYSTEM_CPU_TIME, _CACHED_SYSTEM_CPU
    global _ASYNC_CHECKOUT_LOCK, _LAST_ASYNC_CHECKOUT_FETCH, _CACHED_PENDING, _CACHED_COMPLETED, _CACHED_FAILED
    global _DAILY_BATCH_LOCK, _LAST_DAILY_BATCH_FETCH, _CACHED_DAILY_BATCH
    try:
        now = time.time()
        with _METRICS_LOCK:
            
            if now - _LAST_CPU_TIME >= 1.0:
                _CACHED_CPU = _GLOBAL_PROCESS.cpu_percent(interval=None)
                _LAST_CPU_TIME = now
            
            if now - _LAST_SYSTEM_CPU_TIME >= 1.0:
                _CACHED_SYSTEM_CPU = psutil.cpu_percent(interval=None)
                _LAST_SYSTEM_CPU_TIME = now
                
            cpu_percent = _CACHED_CPU
            system_cpu = _CACHED_SYSTEM_CPU
            
        memory_mb = _GLOBAL_PROCESS.memory_info().rss / (1024 * 1024)
        system_memory = psutil.virtual_memory().percent
    except Exception:
        cpu_percent = 0.0
        memory_mb = 0.0
        system_cpu = 0.0
        system_memory = 0.0

    now = time.time()
    
    if now - _LAST_ASYNC_CHECKOUT_FETCH >= 5.0:
        if _ASYNC_CHECKOUT_LOCK.acquire(blocking=False):
            try:
                _CACHED_PENDING = Order.objects.filter(status="pending").count()
                _CACHED_COMPLETED = Order.objects.filter(status="completed").count()
                _CACHED_FAILED = Order.objects.filter(status="failed").count()
                _LAST_ASYNC_CHECKOUT_FETCH = now
            except Exception:
                pass
            finally:
                _ASYNC_CHECKOUT_LOCK.release()

    
    if now - _LAST_DAILY_BATCH_FETCH >= 5.0:
        if _DAILY_BATCH_LOCK.acquire(blocking=False):
            try:
                _CACHED_DAILY_BATCH = _get_daily_batch_metrics()
                _LAST_DAILY_BATCH_FETCH = now
            except Exception:
                pass
            finally:
                _DAILY_BATCH_LOCK.release()

    payload = {
        "online": online,
        "server": {
            "url": server_url,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "cpu_percent": round(cpu_percent, 2),
            "memory_mb": round(memory_mb, 2),
            "system_cpu_percent": round(system_cpu, 2),
            "system_memory_percent": round(system_memory, 2),
        },
        "system": resource_manager.get_metrics(),
        "checkout_queue": None,
        "db_active_connections": _get_active_db_connections(),
        "error": error,
        "async_checkout": {
            "pending_orders": _CACHED_PENDING,
            "completed_orders": _CACHED_COMPLETED,
            "failed_orders": _CACHED_FAILED,
        },
        "daily_batch": _CACHED_DAILY_BATCH,
        "cache_metrics": _get_cache_metrics(),
    }
    return payload


def _get_daily_batch_metrics():
    latest_report = DailySalesReport.objects.order_by("-date").first()
    if not latest_report:
        return None
    dead_letters = DeadLetterSales.objects.filter(report=latest_report).count()
    return {
        "batch_date": str(latest_report.date),
        "batch_status": latest_report.status,
        "batch_total": latest_report.total_orders,
        "batch_processed": latest_report.processed_orders,
        "batch_revenue": str(latest_report.total_revenue),
        "batch_dead_letters": dead_letters,
        "batch_pdf": latest_report.pdf_report_path or "Not ready"
    }


def _get_cache_metrics():
    from django.core.cache import cache
    try:
        redis_client = cache.client.get_client()
        info = redis_client.info('stats')
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total = hits + misses
        hit_ratio = (hits / total * 100.0) if total > 0 else 0.0
        return {
            "hits": hits,
            "misses": misses,
            "hit_ratio_percent": round(hit_ratio, 2)
        }
    except Exception:
        return {"hits": 0, "misses": 0, "hit_ratio_percent": 0.0}


def system_local_metrics_view(request):
    server_url = f"{request.scheme}://{request.get_host()}"
    exclude_db = request.GET.get("exclude_db", "false").lower() == "true"
    return JsonResponse(_local_metrics_payload(server_url=server_url, exclude_db=exclude_db))


def _fetch_server_metrics(server_url, current_url, exclude_db=False):
    if server_url.rstrip("/") == current_url.rstrip("/"):
        return _local_metrics_payload(server_url=server_url, exclude_db=exclude_db)

    metrics_url = f"{server_url.rstrip('/')}/system/local-metrics"
    if exclude_db:
        metrics_url += "?exclude_db=true"
    request = Request(metrics_url, headers={"Accept": "application/json"})
    try:
        
        with urlopen(request, timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            payload["server"]["url"] = server_url
            return payload
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "online": False,
            "server": {
                "url": server_url,
                "pid": None,
                "hostname": None,
            },
            "system": None,
            "checkout_queue": None,
            "db_active_connections": 0,
            "async_checkout": None,
            "error": str(exc),
        }


def system_metrics_view(request):
    from concurrent.futures import ThreadPoolExecutor
    
    current_url = f"{request.scheme}://{request.get_host()}"
    server_urls = getattr(settings, "MONITORED_SERVER_URLS", [current_url])
    exclude_db = request.GET.get("exclude_db", "false").lower() == "true"
    
    
    with ThreadPoolExecutor(max_workers=len(server_urls)) as executor:
        servers = list(executor.map(
            lambda url: _fetch_server_metrics(url, current_url, exclude_db=exclude_db),
            server_urls
        ))
        
    online_servers = [server for server in servers if server["online"]]

    return JsonResponse(
        {
            "summary": {
                "configured_servers": len(servers),
                "online_servers": len(online_servers),
                "offline_servers": len(servers) - len(online_servers),
            },
            "servers": servers,
        }
    )


def system_dashboard_view(request):
    html = """
<!doctype html>
<html>
  <head>
    <title>System Live Metrics</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { margin: 0; font-family: Arial, sans-serif; background: 
      main { max-width: 1100px; margin: 0 auto; padding: 24px; }
      h1 { font-size: 26px; margin: 0 0 6px; }
      h2 { margin-top: 26px; }
      h3 { margin: 18px 0 10px; }
      .updated { color: 
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
      .metric { background: 
      .label { color: 
      .value { font-size: 28px; font-weight: 700; overflow-wrap: anywhere; }
      .server { background: 
      .server-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
      .status { border-radius: 999px; padding: 4px 10px; font-size: 13px; font-weight: 700; }
      .online { background: 
      .offline { background: 
      pre { overflow: auto; background: 
    </style>
  </head>
  <body>
    <main>
      <h1>System Live Metrics</h1>
      <div class="updated" id="updated">Loading...</div>

      <section>
        <h2>Running Servers</h2>
        <div class="grid" id="summary-grid"></div>
      </section>

      <section>
        <h2>Server Details</h2>
        <div id="servers"></div>
      </section>
      <section>
        <h2>Raw JSON</h2>
        <pre id="raw">{}</pre>
      </section>
    </main>

    <script>
      const labels = {
        configured_servers: "Configured servers",
        online_servers: "Online servers",
        offline_servers: "Offline servers",
        max_workers: "Max workers (Limit)",
        spawned_threads: "Total Threads Alive",
        running_threads: "Busy Threads (Processing)",
        idle_waiting_to_die: "Idle Worker Threads",
        max_queue_size: "Queue Capacity",
        waiting_requests: "Requests Waiting",
        remaining_queue_slots: "Queue Slots Remaining",
        total_capacity: "Max System Concurrency",
        rejected_total: "Lifetime Rejections",
        db_active_connections: "Active DB Connections",
        pending_orders: "Pending Orders (In Queue)",
        completed_orders: "Completed Orders",
        failed_orders: "Failed Orders",
        batch_date: "Report Date",
        batch_status: "Batch Status",
        batch_total: "Total Orders",
        batch_processed: "Processed",
        batch_revenue: "Total Revenue ($)",
        batch_dead_letters: "Dead Letters (Failed)",
        batch_pdf: "PDF Path",
        cpu_percent: "Process CPU Usage",
        memory_mb: "Process Memory Usage",
        system_cpu_percent: "Global System CPU",
        system_memory_percent: "Global System Memory",
        hits: "Cache Hits (Total)",
        misses: "Cache Misses (Total)",
        hit_ratio_percent: "Cache Hit Ratio (%)"
      };

      function metricCards(data) {
        if (!data) return "";
        return Object.entries(data).map(([key, value]) => `
          <div class="metric">
            <div class="label">${labels[key] || key}</div>
            <div class="value">${value}</div>
          </div>
        `).join("");
      }

      function renderGrid(id, data) {
        document.getElementById(id).innerHTML = metricCards(data);
      }

      function renderServer(server, index) {
        const statusClass = server.online ? "online" : "offline";
        const statusText = server.online ? "ONLINE" : "OFFLINE";
        if (!server.online) {
          return `
            <div class="server">
              <div class="server-header">
                <div><strong>Server ${index + 1}</strong><br />${server.server.url}</div>
                <span class="status ${statusClass}">${statusText}</span>
              </div>
              <div class="label">${server.error || "Not reachable"}</div>
            </div>
          `;
        }

        return `
          <div class="server">
            <div class="server-header">
              <div>
                <strong>Server ${index + 1}</strong><br />
                ${server.server.url} · PID ${server.server.pid} · ${server.server.hostname}
              </div>
              <span class="status ${statusClass}">${statusText}</span>
            </div>
            <h3>Physical Hardware Resources</h3>
            <div class="grid">${metricCards(server.server ? {
              cpu_percent: server.server.cpu_percent + " %",
              memory_mb: server.server.memory_mb + " MB",
              system_cpu_percent: server.server.system_cpu_percent + " % (Global)",
              system_memory_percent: server.server.system_memory_percent + " % (Global)",
            } : null)}</div>
            <h3>Thread Pool</h3>
            <div class="grid">${metricCards(server.system ? server.system.thread_pool : null)}</div>
            <h3>Global Queue</h3>
            <div class="grid">${metricCards(server.system ? server.system.global_queue : null)}</div>
            <h3>System Totals</h3>
            <div class="grid">${metricCards(server.system ? {
              total_capacity: server.system.total_capacity,
              rejected_total: server.system.rejected_total,
              db_active_connections: server.db_active_connections !== undefined ? server.db_active_connections : "N/A"
            } : null)}</div>
            <h3>Checkout Queue (Legacy)</h3>
            <div class="grid">${metricCards(server.checkout_queue || {})}</div>
            <h3>Async Checkout (Celery)</h3>
            <div class="grid">${metricCards(server.async_checkout || {})}</div>
            <h3>Daily Sales Batch (Latest)</h3>
            <div class="grid">${metricCards(server.daily_batch || {"status": "No reports yet"})}</div>
            <h3>Redis Cache Performance</h3>
            <div class="grid">${metricCards(server.cache_metrics || {})}</div>
          </div>
        `;
      }

      async function refresh() {
        const response = await fetch("/system/metrics?exclude_db=true", { cache: "no-store" });
        const data = await response.json();
        renderGrid("summary-grid", data.summary);
        document.getElementById("servers").innerHTML =
          data.servers.map(renderServer).join("");
        document.getElementById("raw").textContent = JSON.stringify(data, null, 2);
        document.getElementById("updated").textContent =
          `Updated ${new Date().toLocaleTimeString()}`;
      }

      refresh();
      setInterval(refresh, 1000);
    </script>
  </body>
</html>
"""
    return HttpResponse(html)



urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("", root_view),
    path("system/local-metrics", system_local_metrics_view, name="system-local-metrics"),
    path("system/metrics", system_metrics_view, name="system-metrics"),
    path("system/dashboard", system_dashboard_view, name="system-dashboard"),
    path("", include("store.urls")),
]
