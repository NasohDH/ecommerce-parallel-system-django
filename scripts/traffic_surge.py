import requests
import threading
import time

URL = "http://127.0.0.1:8080/system/health" # Assuming health check endpoint or just hit home page
NUM_REQUESTS = 150
CONCURRENCY = 15

def make_request(i):
    try:
        requests.get("http://127.0.0.1:8080/")
    except Exception:
        pass

print("==========================================")
print("  INITIATING 100x TRAFFIC SURGE SIMULATION")
print("==========================================")
print(f"Target: http://127.0.0.1:8080/")
print(f"Total Requests: {NUM_REQUESTS}")
print(f"Concurrency level: {CONCURRENCY}")
print("Firing requests...")

threads = []
for i in range(NUM_REQUESTS):
    t = threading.Thread(target=make_request, args=(i,))
    threads.append(t)
    t.start()
    
    if len(threads) >= CONCURRENCY:
        for t in threads:
            t.join()
        threads = []
        time.sleep(0.1) # Small delay to sustain RPS just above threshold

for t in threads:
    t.join()

print("\n Surge complete. Check the Load Balancer console to see Auto-Scaling in action!")
