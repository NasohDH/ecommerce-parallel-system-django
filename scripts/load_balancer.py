import os
import sys
import time
import requests
import subprocess

MAX_SERVERS = 3
STATIC_CLUSTER = False  

NODES = [
    {"id": "Server-Alpha", "port": 8001, "active": True, "process": None},
    {"id": "Server-Beta",  "port": 8002, "active": False, "process": None},
    {"id": "Server-Gamma", "port": 8003, "active": False, "process": None},
]

def update_nginx_upstream():
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
            
        
        subprocess.run(
            [nginx_exe_path, "-p", os.path.dirname(nginx_exe_path), "-c", nginx_conf_path, "-s", "reload"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"[Script]  Nginx reloaded (Active: Alpha={'ON' if NODES[0]['active'] else 'OFF'}, Beta={'ON' if NODES[1]['active'] else 'OFF'}, Gamma={'ON' if NODES[2]['active'] else 'OFF'})")
    except Exception as e:
        print(f"[Script] ️ Failed to dynamically reload Nginx: {e}")

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
    python_exe = sys.executable
    manage_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manage.py")
    
    last_surge_time = time.time()
    last_scale_up_time = time.time()  
    session = requests.Session()
    
    while True:
        time.sleep(0.5)
        
        active_nodes = [n for n in NODES if n["active"]]
        active_count = len(active_nodes)
        
        is_overloaded = False
        total_running = 0
        total_max = 0
        
        
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
                    
                    
                    thread_load = in_system / capacity
                    cpu_load = cpu / 100.0
                    node_load = max(thread_load, cpu_load)
                    
                    total_running += int(node_load * capacity)
                    total_max += capacity
                    
                    
                    if running == pool_data.get("max_workers", 20) and active_count < MAX_SERVERS:
                        is_overloaded = True
                        print(f"\n[Monitor] ️  THREAD POOL EXHAUSTED on {node['id']} ({running} threads busy). Scaling up!")
                    elif cpu >= 80.0 and active_count < MAX_SERVERS:
                        is_overloaded = True
                        print(f"\n[Monitor]  CPU OVERLOADED on {node['id']} ({cpu}% CPU utilization). Scaling up!")
            except Exception as e:
                sys.stdout.write(f"\n[Monitor] ️ Error querying {node['id']} metrics: {e}\n")
                sys.stdout.flush()
                
                
                is_overloaded = True
        
        cluster_load_pct = 0.0
        if total_max > 0:
            cluster_load_pct = (total_running / total_max) * 100.0
            
        nginx_conns = get_nginx_active_connections(session)
        
        
        if cluster_load_pct > 70.0 or nginx_conns > 80:
            is_overloaded = True
            
        
        status_msg = f"[Monitor]  Nginx Conns: {nginx_conns} | Active Nodes: {active_count}"
        if is_overloaded:
            status_msg += " (Overloaded)"
        else:
            status_msg += " "
        sys.stdout.write(f"\r{status_msg}")
        sys.stdout.flush()
        
        if STATIC_CLUSTER:
            continue
            
        now = time.time()
        
        
        if is_overloaded:
            last_surge_time = now
            if active_count < MAX_SERVERS:
                for node in NODES:
                    if not node["active"]:
                        print(f"\n[Script] PROVISIONING NEW SERVER: {node['id']} on Port {node['port']}")
                        
                        process = subprocess.Popen(
                            [python_exe, "-m", "waitress", f"--listen=127.0.0.1:{node['port']}", "--threads=40", "ecommerce_backend.wsgi:application"],
                            cwd=os.path.dirname(manage_py),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        node["process"] = process
                        
                        print(f"[Script]  Booting {node['id']}...")
                        time.sleep(5)  
                        
                        
                        node["active"] = True
                        update_nginx_upstream()
                        last_scale_up_time = time.time()  
                        print(f"[Script]  {node['id']} is ONLINE and receiving traffic.\n")
                        break
        
        
        elif active_count > 1:
            
            scale_up_elapsed = now - last_scale_up_time
            if scale_up_elapsed < 120:
                time_left = int(120 - scale_up_elapsed)
                sys.stdout.write(f"\r[Monitor]  Scale-up cooldown active. Scale-down blocked for {time_left} seconds...          ")
                sys.stdout.flush()
                continue
                
            node_to_kill = active_nodes[-1]
            
            
            is_idle = (cluster_load_pct < 15.0)
            
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
            print(f"[Script]  TERMINATING IDLE SERVER: {node_to_kill['id']} to save CPU/RAM.")
            
            
            node_to_kill["active"] = False
            update_nginx_upstream()
            
            
            time.sleep(1)
            
            
            if node_to_kill["process"]:
                node_to_kill["process"].terminate()
                node_to_kill["process"] = None
            else:
                
                try:
                    if sys.platform.startswith("win"):
                        out = subprocess.check_output(f"netstat -ano | findstr :{node_to_kill['port']}", shell=True).decode()
                        pids = set()
                        for line in out.splitlines():
                            parts = line.strip().split()
                            if parts and len(parts) >= 5:
                                
                                pids.add(parts[-1])
                        for pid in pids:
                            if pid.isdigit() and int(pid) > 0:
                                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                
            print(f"[Script]  {node_to_kill['id']} has been shut down.\n")
            last_surge_time = now

if __name__ == "__main__":
    
    python_exe = sys.executable
    manage_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manage.py")
    
    if STATIC_CLUSTER:
        for node in NODES:
            node["active"] = True
            print(f"[System] Starting {node['id']} on Port {node['port']}")
            node["process"] = subprocess.Popen(
                [python_exe, "-m", "waitress", f"--listen=127.0.0.1:{node['port']}", "--threads=40", "ecommerce_backend.wsgi:application"],
                cwd=os.path.dirname(manage_py),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        
        update_nginx_upstream()
        
    else:
        primary_node = NODES[0]
        
        update_nginx_upstream()
        
        print(f"[System] Starting Primary Node: {primary_node['id']} on Port {primary_node['port']}")
        primary_node["process"] = subprocess.Popen(
            [python_exe, "-m", "waitress", f"--listen=127.0.0.1:{primary_node['port']}", "--threads=40", "ecommerce_backend.wsgi:application"],
            cwd=os.path.dirname(manage_py),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        print("[System]  Waiting for Server-Alpha to boot...")
        time.sleep(5)
        print("[System]  Server-Alpha is ready!")
        print("==========================================")
    
    try:
        monitor_and_autoscale()
    except KeyboardInterrupt:
        print("\n[System] Shutting down Script and terminating all nodes...")
        for node in NODES:
            if node["process"]:
                node["process"].terminate()
        
        NODES[1]["active"] = False
        NODES[2]["active"] = False
        update_nginx_upstream()
