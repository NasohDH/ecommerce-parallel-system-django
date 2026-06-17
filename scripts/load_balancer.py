import os
import sys
import time
import threading
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# ️ LOAD BALANCER & AUTO-SCALER CONFIG
# ==========================================
MAX_SERVERS = 3
SURGE_THRESHOLD_RPS = 10.0  # Requests Per Second to trigger scaling
MAX_WORKERS_PER_NODE = 40   # Max proxy threads per backend node (matches SYSTEM_MAX_WORKERS)

# Global proxy server reference — used by the auto-scaler to create/destroy node pools
_proxy_server = None

# Weighted Round Robin configuration
# Node 1: Heavy Duty (Weight 5)
# Node 2: Standard (Weight 3)
# Node 3: Backup/Light (Weight 1)
NODES = [
    {"id": "Server-Alpha", "port": 8001, "weight": 5, "active": True, "process": None},
    {"id": "Server-Beta",  "port": 8002, "weight": 5, "active": False, "process": None},
    {"id": "Server-Gamma", "port": 8003, "weight": 5, "active": False, "process": None},
]

# WRR State variables
current_index = -1
current_weight = 0
request_timestamps = []
active_connections = 0  #  REAL-TIME TRACKING
metrics_lock = threading.Lock()
_wrr_lock = threading.Lock()    # Protects current_index & current_weight across threads

# Thread-local storage: every proxy thread knows which node it belongs to.
# Set once by ThreadPoolExecutor's initializer when the thread is first created.
_thread_local = threading.local()

# ==========================================
# ️ WEIGHTED ROUND ROBIN ALGORITHM
# ==========================================
def get_max_weight(active_nodes):
    return max([n["weight"] for n in active_nodes], default=0)

def get_next_node():
    global current_index, current_weight
    with _wrr_lock:  # Atomic read-modify-write: only one thread selects a node at a time
        active_nodes = [n for n in NODES if n["active"]]

        if not active_nodes:
            return None

        while True:
            current_index = (current_index + 1) % len(active_nodes)
            if current_index == 0:
                current_weight -= 1  # Simplified GCD of 1
                if current_weight <= 0:
                    current_weight = get_max_weight(active_nodes)
                    if current_weight == 0:
                        return None
            if active_nodes[current_index]["weight"] >= current_weight:
                return active_nodes[current_index]

# ==========================================
#  REVERSE PROXY HANDLER
# ==========================================
class PooledHTTPServer(HTTPServer):
    """
    Per-node dynamic thread pool proxy server.

    Each active backend node gets its own ThreadPoolExecutor with up to
    MAX_WORKERS_PER_NODE threads. Threads are:
      - Created on demand (not pre-spawned at startup)
      - Reused across requests (never destroyed after a single request)
      - Capped at MAX_WORKERS_PER_NODE per node
      - Automatically wound down when the node is removed
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create a pool for every node that is already active at startup
        for node in NODES:
            if node["active"]:
                self._create_executor(node)

    def _create_executor(self, node):
        """Spin up a dynamic thread pool for this node."""
        def _init_thread(n=node):
            # Runs ONCE per thread when it is first created inside the pool.
            # The thread then carries this node reference for its entire lifetime.
            _thread_local.node = n

        node["executor"] = ThreadPoolExecutor(
            max_workers=MAX_WORKERS_PER_NODE,
            thread_name_prefix=f"proxy-{node['id']}",
            initializer=_init_thread,
        )
        print(f"[Pool] Node {node['id']}: dynamic thread pool created (max {MAX_WORKERS_PER_NODE} threads, created on demand)")

    def _destroy_executor(self, node):
        """Shut down this node's thread pool cleanly (does not wait for in-flight requests)."""
        executor = node.pop("executor", None)
        if executor:
            executor.shutdown(wait=False)
            print(f"[Pool] Node {node['id']}: thread pool shut down")

    def process_request(self, request, client_address):
        """Route each accepted connection to the correct node's thread pool."""
        node = get_next_node()
        if node is None or node.get("executor") is None:
            try:
                request.close()
            except Exception:
                pass
            return
        # Submit to THIS node's pool — the thread will already have _thread_local.node set
        node["executor"].submit(self._process_in_pool, request, client_address)

    def _process_in_pool(self, request, client_address):
        """Runs on a pooled proxy thread. Calls the standard handler pipeline."""
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

    def server_close(self):
        for node in NODES:
            self._destroy_executor(node)
        super().server_close()

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default HTTP logging to keep console clean
        pass

    def handle_request(self):
        global active_connections
        # 1. Record Metrics for Auto-Scaler
        with metrics_lock:
            request_timestamps.append(time.time())
            active_connections += 1
            
        try:
            # 2. The node was already selected by process_request (WRR) and is stored
            # in the thread-local set when this thread was first created in the pool.
            node = getattr(_thread_local, "node", None)
            if not node:
                self.send_error(503, "No backend servers available")
                return

            # 3. Forward the Request
            target_url = f"http://127.0.0.1:{node['port']}{self.path}"
            
            #  READ THE DATA: We must forward the POST body!
            content_length = int(self.headers.get('Content-Length', 0))
            request_body = self.rfile.read(content_length) if content_length > 0 else None
            
            try:
                # Set timeout to None so we wait indefinitely for the backend, 
                # exactly like a direct connection would.
                resp = requests.request(
                    method=self.command,
                    url=target_url,
                    headers={key: val for (key, val) in self.headers.items() if key != 'Host'},
                    data=request_body,
                    timeout=None
                )
                
                # 4. Return the Response
                self.send_response(resp.status_code)
                for key, val in resp.headers.items():
                    if key not in ['Transfer-Encoding', 'Content-Encoding']:
                        self.send_header(key, val)
                self.end_headers()
                
                try:
                    self.wfile.write(resp.content)
                except (ConnectionError, BrokenPipeError):
                    # Client disconnected before we could finish sending data.
                    # Normal during heavy stress tests or when client times out.
                    pass
                
            except requests.exceptions.RequestException as e:
                try:
                    self.send_error(502, f"Bad Gateway: Server {node['id']} failed to respond.")
                except:
                    pass
        finally:
            with metrics_lock:
                active_connections -= 1

    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()

# ==========================================
#  SURGE DETECTION & AUTO-SCALING THREAD
# ==========================================
def monitor_and_autoscale():
    print("[Monitor] ️  System monitoring and auto-scaler started.")
    python_exe = sys.executable
    manage_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manage.py")
    
    last_surge_time = time.time()
    
    while True:
        time.sleep(2)
        now = time.time()
        
        with metrics_lock:
            # Keep only requests from the last 10 seconds to calculate RPS
            global request_timestamps
            request_timestamps = [t for t in request_timestamps if now - t < 10]
            current_rps = len(request_timestamps) / 10.0
            current_in_flight = active_connections
            
        active_nodes = [n for n in NODES if n["active"]]
        active_count = len(active_nodes)
        
        # 1. Detect Surge
        if current_rps >= SURGE_THRESHOLD_RPS:
            last_surge_time = now
            if active_count < MAX_SERVERS:
                #  SMART SCALING: Calculate load using both proxy-level in-flight requests AND server queues
                is_overloaded = False
                total_running = current_in_flight  # Proxy knows exactly how many it's waiting on
                total_max = 0
                
                for node in active_nodes:
                    try:
                        metrics_url = f"http://127.0.0.1:{node['port']}/system/metrics"
                        resp = requests.get(metrics_url, timeout=2)
                        if resp.status_code == 200:
                            data = resp.json()
                            sys_data = data.get("system", {})
                            pool_data = sys_data.get("thread_pool", {})
                            
                            running = pool_data.get("running_threads", 0)
                            in_system = sys_data.get("total_in_system", 0)
                            capacity = sys_data.get("total_capacity", 120)
                            
                            total_running += in_system
                            total_max += capacity
                            
                            #  AGGRESSIVE SCALING: If threads are 100% full (20/20), scale up NOW!
                            if running >= pool_data.get("max_workers", 20):
                                is_overloaded = True
                                print(f"\n[Monitor] ️  THREAD POOL EXHAUSTED on {node['id']} ({running} threads busy). Scaling up!")
                    except Exception:
                        pass
                
                if not is_overloaded and total_max > 0:
                    current_load = total_running / total_max
                    if current_load > 0.70:
                        is_overloaded = True
                        print(f"\n[Monitor]  SERVER OVERLOAD DETECTED! (Total Load: {current_load*100:.1f}%)")
                    else:
                        sys.stdout.write(f"\r[Monitor]  Traffic spike detected. Load: {current_load*100:.1f}% (Healthy)          ")
                        sys.stdout.flush()
                elif total_max == 0:
                    is_overloaded = True
                
                if is_overloaded:
                    # 2. Auto-Scale Provisioning
                    for node in NODES:
                        if not node["active"]:
                            print(f"[Auto-Scale]  PROVISIONING NEW SERVER: {node['id']} on Port {node['port']} (Weight: {node['weight']})")
                            node["active"] = True

                            # Create the thread pool BEFORE the node starts receiving traffic
                            if _proxy_server:
                                _proxy_server._create_executor(node)

                            # Boot up a new Django instance silently
                            process = subprocess.Popen(
                                [python_exe, manage_py, "runserver", "--noreload", str(node['port'])],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                            node["process"] = process

                            print(f"[Auto-Scale]  {node['id']} is now ONLINE and receiving traffic.\n")
                            # Wait a moment for server to boot before next check
                            time.sleep(5)
                            break
        
        # 3. Auto-Scale Down (Scale In)
        # We only scale down if we have extra servers AND the load balancer has been quiet for 120 seconds (2 mins).
        elif active_count > 1:
            idle_time = now - last_surge_time
            node_to_kill = active_nodes[-1] 
            
            # ️ SAFETY CHECK: Is the server secretly still working on a huge backlog?
            is_busy = False
            try:
                metrics_url = f"http://127.0.0.1:{node_to_kill['port']}/system/metrics"
                # Increase timeout to 5s to handle high-load lag
                resp = requests.get(metrics_url, timeout=5)
                if resp.status_code == 200:
                    sys_data = resp.json().get("system", {})
                    if sys_data.get("total_in_system", 0) > 0:
                        is_busy = True
                else:
                    # If server returns error, assume it's struggling/busy
                    is_busy = True
            except (requests.Timeout, requests.ConnectionError):
                # If we timeout or can't connect during a load period, the server is likely pegged at 100% CPU.
                # Do NOT kill it; assume it's busy.
                is_busy = True
            except Exception:
                pass 
                
            if is_busy:
                # The server is still chewing through work or timing out!
                last_surge_time = now
                sys.stdout.write(f"\r[Monitor] ️ {node_to_kill['id']} is UNRESPONSIVE or BUSY. Resetting idle timer...          ")
                sys.stdout.flush()
                continue
            
            # It's truly idle. Show the countdown!
            if idle_time < 120:
                time_left = int(120 - idle_time)
                sys.stdout.write(f"\r[Monitor]  Traffic low. Shutting down {node_to_kill['id']} in {time_left} seconds...          ")
                sys.stdout.flush()
                continue
            
            print(f"\n\n[Monitor]  IDLE DETECTED! (Proxy and Server both idle for 2 minutes)")
            print(f"[Auto-Scale]  TERMINATING IDLE SERVER: {node_to_kill['id']} to save CPU/RAM.")
            
            # Remove from rotation first so no new requests are routed here
            node_to_kill["active"] = False

            # Destroy the thread pool — no new proxy threads will be created for this node
            if _proxy_server:
                _proxy_server._destroy_executor(node_to_kill)

            # Terminate the Django process
            if node_to_kill["process"]:
                node_to_kill["process"].terminate()
                node_to_kill["process"] = None

            print(f"[Auto-Scale]  {node_to_kill['id']} has been shut down.\n")
            
            # Reset surge time so we wait 120s before killing the next one
            last_surge_time = now

# ==========================================
#  MAIN ENTRY POINT
# ==========================================
if __name__ == "__main__":
    print("==========================================")
    print("LOAD BALANCER STARTING")
    print("==========================================")
    
    # Start the primary server immediately
    primary_node = NODES[0]
    python_exe = sys.executable
    manage_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manage.py")
    
    print(f"[System] Starting Primary Node: {primary_node['id']} on Port {primary_node['port']}")
    primary_node["process"] = subprocess.Popen(
        [python_exe, manage_py, "runserver", "--noreload", str(primary_node['port'])],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Start Monitoring Thread
    monitor_thread = threading.Thread(target=monitor_and_autoscale, daemon=True)
    monitor_thread.start()
    
    # Start Reverse Proxy
    PORT = 8080
    _proxy_server = PooledHTTPServer(("0.0.0.0", PORT), ProxyHTTPRequestHandler)
    print(f"[System]  Load Balancer listening on http://127.0.0.1:{PORT}")
    print(f"[System] ️  Algorithm: Weighted Round Robin")
    print(f"[System]  Thread model: dynamic pool, {MAX_WORKERS_PER_NODE} threads max per node")
    print(f"[System]  Auto-Scaling Policy: Provision if RPS > {SURGE_THRESHOLD_RPS} (Max {MAX_SERVERS} nodes)")
    print("==========================================")

    try:
        _proxy_server.serve_forever()
    except KeyboardInterrupt:
        print("\n[System] Shutting down Load Balancer and terminating all nodes...")
        _proxy_server.server_close()  # Cleanly shuts down all node thread pools
        for node in NODES:
            if node.get("process"):
                node["process"].terminate()
        print("[System] Goodbye.")
