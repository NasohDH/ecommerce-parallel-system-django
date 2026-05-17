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

from ecommerce_backend.openapi import OPENAPI_SCHEMA
from ecommerce_backend.resource_manager import resource_manager
from store.services.checkout_queue import checkout_queue
from store.models import Order, DailySalesReport, DeadLetterSales

# Persistent global process handle so cpu_percent retains state between calls
_GLOBAL_PROCESS = psutil.Process(os.getpid())
_GLOBAL_PROCESS.cpu_percent(interval=None)
psutil.cpu_percent(interval=None)
_METRICS_LOCK = Lock()

# Caching state to prevent rapid polling from returning 0% due to clock tick resolution
import time
_LAST_CPU_TIME = 0.0
_CACHED_CPU = 0.0
_LAST_SYSTEM_CPU_TIME = 0.0
_CACHED_SYSTEM_CPU = 0.0


def root_view(request):
    return JsonResponse({"message": "E-commerce API is running"})


def openapi_view(request):
    return JsonResponse(OPENAPI_SCHEMA)


def _local_metrics_payload(server_url=None, online=True, error=None, exclude_db=False):
    global _GLOBAL_PROCESS, _METRICS_LOCK, _LAST_CPU_TIME, _CACHED_CPU, _LAST_SYSTEM_CPU_TIME, _CACHED_SYSTEM_CPU
    try:
        now = time.time()
        with _METRICS_LOCK:
            # Only update process CPU if at least 1.0 seconds have elapsed since last measurement
            if now - _LAST_CPU_TIME >= 1.0:
                _CACHED_CPU = _GLOBAL_PROCESS.cpu_percent(interval=None)
                _LAST_CPU_TIME = now
            # Only update system CPU if at least 1.0 seconds have elapsed since last measurement
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
        "checkout_queue": checkout_queue.get_metrics(),
        "error": error,
    }
    if not exclude_db:
        payload["async_checkout"] = {
            "pending_orders": Order.objects.filter(status="pending").count(),
            "completed_orders": Order.objects.filter(status="completed").count(),
            "failed_orders": Order.objects.filter(status="failed").count(),
        }
    else:
        payload["async_checkout"] = None
        
    payload["daily_batch"] = _get_daily_batch_metrics()
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
        # Set timeout to 1.0s to allow successful retrieval under heavy concurrency
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
            "async_checkout": None,
            "error": str(exc),
        }


def system_metrics_view(request):
    from concurrent.futures import ThreadPoolExecutor
    
    current_url = f"{request.scheme}://{request.get_host()}"
    server_urls = getattr(settings, "MONITORED_SERVER_URLS", [current_url])
    exclude_db = request.GET.get("exclude_db", "false").lower() == "true"
    
    # Query all servers in parallel so we don't block the thread sequentially!
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
      body { margin: 0; font-family: Arial, sans-serif; background: #f6f7f9; color: #1f2937; }
      main { max-width: 1100px; margin: 0 auto; padding: 24px; }
      h1 { font-size: 26px; margin: 0 0 6px; }
      h2 { margin-top: 26px; }
      h3 { margin: 18px 0 10px; }
      .updated { color: #6b7280; margin-bottom: 18px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
      .metric { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; }
      .label { color: #6b7280; font-size: 13px; margin-bottom: 8px; overflow-wrap: anywhere; }
      .value { font-size: 28px; font-weight: 700; overflow-wrap: anywhere; }
      .server { background: #fff; border: 1px solid #d1d5db; border-radius: 8px; padding: 16px; margin-top: 14px; }
      .server-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
      .status { border-radius: 999px; padding: 4px 10px; font-size: 13px; font-weight: 700; }
      .online { background: #dcfce7; color: #166534; }
      .offline { background: #fee2e2; color: #991b1b; }
      pre { overflow: auto; background: #111827; color: #f9fafb; padding: 14px; border-radius: 8px; }
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
        idle_waiting_to_die: "Idle Threads (Ready & Waiting)",
        max_queue_size: "Queue capacity",
        waiting_requests: "Waiting requests",
        remaining_queue_slots: "Remaining queue slots",
        total_capacity: "Total capacity",
        total_in_system: "Total in system",
        remaining_capacity: "Remaining capacity",
        rejected_total: "Rejected",
        waiting_tasks: "Checkout in queue",
        running_tasks: "Checkout processing",
        tracked_jobs: "Tracked jobs",
        enqueued_total: "Checkout requests in",
        completed_total: "Checkout done",
        failed_total: "Checkout failed",
        worker_alive: "Checkout worker alive",
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
        system_memory_percent: "Global System Memory"
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
              total_in_system: server.system.total_in_system,
              remaining_capacity: server.system.remaining_capacity,
              rejected_total: server.system.rejected_total
            } : null)}</div>
            <h3>Checkout Queue (Legacy)</h3>
            <div class="grid">${metricCards(server.checkout_queue || {})}</div>
            <h3>Async Checkout (Celery)</h3>
            <div class="grid">${metricCards(server.async_checkout || {})}</div>
            <h3>Daily Sales Batch (Latest)</h3>
            <div class="grid">${metricCards(server.daily_batch || {"status": "No reports yet"})}</div>
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


def scalar_docs_view(request):
    html = """
<!doctype html>
<html>
  <head>
    <title>E-commerce Backend - Scalar</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
  <body>
    <script
      id="api-reference"
      data-url="/openapi.json"
      data-theme="default"
    ></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
  </body>
</html>
"""
    return HttpResponse(html)


urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("", root_view),
    path("docs", scalar_docs_view, name="scalar-docs"),
    path("openapi.json", openapi_view, name="openapi-schema"),
    path("system/local-metrics", system_local_metrics_view, name="system-local-metrics"),
    path("system/metrics", system_metrics_view, name="system-metrics"),
    path("system/dashboard", system_dashboard_view, name="system-dashboard"),
    path("", include("store.urls")),
]
