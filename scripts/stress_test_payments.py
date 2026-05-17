import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup Django environment
sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")

import django
django.setup()

from store.models import User, Product, Cart, CartItem, Order
from store.services.order.order_checkout import checkout_cart
from django.db import connection

def setup_test_data(num_users):
    print(f"Setting up {num_users} users with carts and multiple products...")
    
    # Create 50 different products to avoid row lock contention
    # (If everyone buys the same phone, only one can check out at a time!)
    products = []
    for i in range(50):
        p, _ = Product.objects.get_or_create(
            name=f"Parallel Product {i}",
            defaults={"price": 10.0, "stock_quantity": 10000}
        )
        p.stock_quantity = 10000
        p.save()
        products.append(p)

    test_users = []
    
    # Create or update users
    for i in range(num_users):
        username = f"stress_user_{i}"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@test.com", "balance": 10000.0}
        )
        user.balance = 10000.0
        user.save()
        
        # Reset Cart and pick a random product
        cart, _ = Cart.objects.get_or_create(user=user)
        CartItem.objects.filter(cart=cart).delete()
        
        # Pick one of our 50 products based on user index
        selected_product = products[i % 50]
        CartItem.objects.create(cart=cart, product=selected_product, quantity=1)
        
        test_users.append(user.id)
        
    print("Setup complete.")
    return test_users

def run_stress_test():
    NUM_REQUESTS = 500
    
    print("="*50)
    print("ASYNC PAYMENT STRESS TEST")
    print("="*50)
    print("Note: Make sure your Celery worker is running!")
    
    user_ids = setup_test_data(NUM_REQUESTS)
    
    print(f"\nFiring {NUM_REQUESTS} checkout requests simultaneously...")
    start_time = time.time()
    
    success_count = 0
    error_count = 0
    
    import json
    from urllib.request import Request, urlopen
    
    def hit_endpoint(uid):
        url = "http://127.0.0.1:8080/orders/checkout"
        data = json.dumps({"user_id": uid}).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    # We now send real HTTP requests to your web server so the ResourceManager
    # will register the incoming traffic and bump the "Running threads" count.
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(hit_endpoint, uid): uid for uid in user_ids}
        for future in as_completed(futures):
            try:
                order_data = future.result()
                if order_data.get("status") == "pending":
                    success_count += 1
            except Exception as e:
                if error_count == 0:
                    print(f"First error encountered: {e}")
                error_count += 1

    elapsed = time.time() - start_time
    print(f"\nAll requests sent to queue in {elapsed:.2f} seconds.")
    print(f"Successfully enqueued: {success_count}")
    print(f"Errors during enqueue: {error_count}")
    
    print("\nGo check your Dashboard (http://127.0.0.1:8080/system/dashboard)!")
    print("You will see 'Pending Orders' jump up, and then slowly drop as Celery processes them into 'Completed Orders'.")

if __name__ == "__main__":
    run_stress_test()
