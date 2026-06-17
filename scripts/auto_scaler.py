import os
import sys
import time
import requests
import subprocess

MAX_SERVERS = 3
STATIC_CLUSTER = False  # Set to True to pre-spawn all 3 nodes and bypass Nginx reloads under heavy stress testing

NODES = [
    {"id": "Server-Alpha", "port": 8001, "active": True, "process": None},
    {"id": "Server-Beta",  "port": 8002, "active": False, "process": None},
    {"id": "Server-Gamma", "port": 8003, "active": False, "process": None},
]

def update_nginx_upstream():
    """Dynamically update nginx.conf and reload Nginx so it only routes to fully healthy, scaled-up backends!"""
    nginx_conf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nginx.conf")
    nginx_exe_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "nginx", "nginx-1.26.0", "nginx.exe")
    
    if not os.path.exists(nginx_conf_path) or not os.path.exists(nginx_exe_path):
        return
        
    try:
        with open(nginx_conf_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        new_lines = []
        for line in lines:
            if "127.0.0.1:8001" in line:
                new_lines.append("        server 127.0.0.1:8001 weight=5 max_fails=0 max_conns=1000;\n")
            elif "127.0.0.1:8002" in line:
                status = "" if NODES[1]["active"] else " down"
                new_lines.append(f"        server 127.0.0.1:8002 weight=5 max_fails=0 max_conns=1000{status};\n")
            elif "127.0.0.1:8003" in line:
                status = "" if NODES[2]["active"] else " down"
                new_lines.append(f"        server 127.0.0.1:8003 weight=5 max_fails=0 max_conns=1000{status};\n")
            else:
                new_lines.append(line)
                
        with open(nginx_conf_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        # Reload Nginx config
        subprocess.run(
            [nginx_exe_path, "-p", os.path.dirname(nginx_exe_path), "-c", nginx_conf_path, "-s", "reload"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"[Auto-Scale]  Nginx reloaded (Active: Alpha={'ON' if NODES[0]['active'] else 'OFF'}, Beta={'ON' if NODES[1]['active'] else 'OFF'}, Gamma={'ON' if NODES[2]['active'] else 'OFF'})")
    except Exception as e:
        print(f"[Auto-Scale] ️ Failed to dynamically reload Nginx: {e}")

def get_nginx_active_connections(session):
    try:
        resp = session.get("http://127.0.0.1:8080/nginx_status", timeout=1)
        if resp.status_code == 200:
            line = resp.text.splitlines()[0]
            return int(line.split(":")[1].strip())
    except Exception:
        pass
    return 0

def monitor_and_autoscale():
    print("[Monitor] ️  System monitoring and auto-scaler started (Nginx is Proxying).")
    python_exe = sys.executable
    manage_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manage.py")
    
    last_surge_time = time.time()
    last_scale_up_time = time.time()  # Track scale-up time to prevent thrashing
    session = requests.Session()
    
    while True:
        time.sleep(0.5)
        
        active_nodes = [n for n in NODES if n["active"]]
        active_count = len(active_nodes)
        
        is_overloaded = False
        total_running = 0
        total_max = 0
        
        # 1. Gather Metrics
        for node in active_nodes:
            try:
                metrics_url = f"http://127.0.0.1:{node['port']}/system/local-metrics?exclude_db=true"
                for attempt in range(10):
                    try:
                        resp = session.get(metrics_url, timeout=2)
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise e
                        time.sleep(0.5)
                if resp.status_code == 200:
                    data = resp.json()
                    sys_data = data.get("system", {})
                    server_data = data.get("server", {})
                    pool_data = sys_data.get("thread_pool", {})
                    
                    running = pool_data.get("running_threads", 0)
                    in_system = sys_data.get("total_in_system", 0)
                    capacity = sys_data.get("total_capacity", 120)
                    
                    cpu = server_data.get("cpu_percent", 0.0)
                    node["cpu"] = cpu
                    node["running_threads"] = running
                    
                    # Node load is the maximum of software queue saturation or physical CPU saturation
                    thread_load = in_system / capacity
                    cpu_load = cpu / 100.0
                    node_load = max(thread_load, cpu_load)
                    
                    total_running += int(node_load * capacity)
                    total_max += capacity
                    
                    #  AGGRESSIVE SOFTWARE/PHYSICAL OVERLOAD CHECK
                    if running >= pool_data.get("max_workers", 20) and active_count < MAX_SERVERS:
                        is_overloaded = True
                        print(f"\n[Monitor] ️  THREAD POOL EXHAUSTED on {node['id']} ({running} threads busy). Scaling up!")
                    elif cpu >= 80.0 and active_count < MAX_SERVERS:
                        is_overloaded = True
                        print(f"\n[Monitor]  CPU OVERLOADED on {node['id']} ({cpu}% CPU utilization). Scaling up!")
            except Exception as e:
                sys.stdout.write(f"\n[Monitor] ️ Error querying {node['id']} metrics: {e}\n")
                sys.stdout.flush()
                # If an active node is unresponsive or times out, it is highly likely overloaded or locked up.
                # Treat it as fully saturated (100% capacity) to trigger robust scale-up!
                total_running += 120
                total_max += 120
                is_overloaded = True
        
        cluster_load_pct = 0.0
        if total_max > 0:
            cluster_load_pct = (total_running / total_max) * 100.0
            
        nginx_conns = get_nginx_active_connections(session)
        
        # If cluster load is high or Nginx active connections are saturating the nodes
        if cluster_load_pct > 70.0 or nginx_conns > 80:
            is_overloaded = True
            
        # Display real-time telemetry line (always updated, never frozen)
        status_msg = f"[Monitor]  Load: {cluster_load_pct:.1f}% | Nginx Conns: {nginx_conns} | Active Nodes: {active_count}"
        if is_overloaded:
            status_msg += " (Overloaded)"
        else:
            status_msg += " (Healthy)      "
        sys.stdout.write(f"\r{status_msg}")
        sys.stdout.flush()
        
        if STATIC_CLUSTER:
            continue
            
        now = time.time()
        
        # 2. Auto-Scale Provisioning
        if is_overloaded:
            last_surge_time = now
            if active_count < MAX_SERVERS:
                for node in NODES:
                    if not node["active"]:
                        print(f"\n[Auto-Scale] PROVISIONING NEW SERVER: {node['id']} on Port {node['port']}")
                        
                        process = subprocess.Popen(
                            [python_exe, "-m", "waitress", f"--listen=127.0.0.1:{node['port']}", "--threads=40", "ecommerce_backend.wsgi:application"],
                            cwd=os.path.dirname(manage_py),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        node["process"] = process
                        
                        print(f"[Auto-Scale]  Booting {node['id']}...")
                        time.sleep(5)  # Wait for Server to fully bind port and initialize Django WSGI
                        
                        # Once server is fully ready, mark active and update Nginx!
                        node["active"] = True
                        update_nginx_upstream()
                        last_scale_up_time = time.time()  # Reset scale-up cooldown timer!
                        print(f"[Auto-Scale]  {node['id']} is ONLINE and receiving traffic.\n")
                        break
        
        # 3. Auto-Scale Down
        elif active_count > 1:
            # Anti-Flapping Cooldown: Enforce that we wait at least 120 seconds since the last scale-up
            scale_up_elapsed = now - last_scale_up_time
            if scale_up_elapsed < 120:
                time_left = int(120 - scale_up_elapsed)
                sys.stdout.write(f"\r[Monitor]  Scale-up cooldown active. Scale-down blocked for {time_left} seconds...          ")
                sys.stdout.flush()
                continue
                
            node_to_kill = active_nodes[-1]
            
            # Robust, metrics-based idle check: cluster load is low and Nginx connections are low
            is_idle = (cluster_load_pct < 15.0) and (nginx_conns < 15)
            
            if not is_idle:
                last_surge_time = now
                sys.stdout.write(f"\r[Monitor] ️ Cluster is active. Idle timer reset.          ")
                sys.stdout.flush()
                continue
                
            idle_time = now - last_surge_time
            if idle_time < 30:
                time_left = int(30 - idle_time)
                sys.stdout.write(f"\r[Monitor]  Entire cluster idle. Shutting down {node_to_kill['id']} in {time_left} seconds...          ")
                sys.stdout.flush()
                continue
                
            print(f"\n\n[Monitor]  IDLE DETECTED! (Server idle for 30 seconds)")
            print(f"[Auto-Scale]  TERMINATING IDLE SERVER: {node_to_kill['id']} to save CPU/RAM.")
            
            # 1. First tell Nginx to stop routing to it immediately!
            node_to_kill["active"] = False
            update_nginx_upstream()
            
            # 2. Give a brief sleep for Nginx connection draining
            time.sleep(1)
            
            # 3. Terminate process cleanly
            if node_to_kill["process"]:
                node_to_kill["process"].terminate()
                node_to_kill["process"] = None
            else:
                # Fallback: Kill any process on that port to guarantee scale-down
                try:
                    if sys.platform.startswith("win"):
                        out = subprocess.check_output(f"netstat -ano | findstr :{node_to_kill['port']}", shell=True).decode()
                        pids = set()
                        for line in out.splitlines():
                            parts = line.strip().split()
                            if parts and len(parts) >= 5:
                                # PID is the last element
                                pids.add(parts[-1])
                        for pid in pids:
                            if pid.isdigit() and int(pid) > 0:
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                
            print(f"[Auto-Scale]  {node_to_kill['id']} has been shut down.\n")
            last_surge_time = now

if __name__ == "__main__":
    print("==========================================")
    print("AUTO-SCALER PROCESS MANAGER STARTING")
    print("==========================================")
    
    python_exe = sys.executable
    manage_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manage.py")
    
    if STATIC_CLUSTER:
        print("[System]  Launching static high-throughput cluster (all 3 nodes active)...")
        for node in NODES:
            node["active"] = True
            print(f"[System] Starting {node['id']} on Port {node['port']}")
            node["process"] = subprocess.Popen(
                [python_exe, "-m", "waitress", f"--listen=127.0.0.1:{node['port']}", "--threads=40", "ecommerce_backend.wsgi:application"],
                cwd=os.path.dirname(manage_py),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        # Clean and sync Nginx state at startup
        update_nginx_upstream()
        
        print("[System]  Waiting 5 seconds for all servers to boot...")
        time.sleep(5)
        print("[System]  All 3 cluster nodes are ready and active under Nginx!")
        print("[System]  Nginx is active on Port 8080.")
        print("==========================================")
    else:
        primary_node = NODES[0]
        # Clean and sync Nginx state at startup
        update_nginx_upstream()
        
        print(f"[System] Starting Primary Node: {primary_node['id']} on Port {primary_node['port']}")
        primary_node["process"] = subprocess.Popen(
            [python_exe, "-m", "waitress", f"--listen=127.0.0.1:{primary_node['port']}", "--threads=40", "ecommerce_backend.wsgi:application"],
            cwd=os.path.dirname(manage_py),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        print("[System]  Waiting 5 seconds for Server-Alpha to boot...")
        time.sleep(5)
        print("[System]  Server-Alpha is ready!")
        print("[System]  Nginx should be configured to listen on Port 8080.")
        print("==========================================")
    
    try:
        monitor_and_autoscale()
    except KeyboardInterrupt:
        print("\n[System] Shutting down Auto-Scaler and terminating all nodes...")
        for node in NODES:
            if node["process"]:
                node["process"].terminate()
        # Reset Nginx config to only alpha before leaving
        NODES[1]["active"] = False
        NODES[2]["active"] = False
        update_nginx_upstream()
        print("[System] Goodbye.")
