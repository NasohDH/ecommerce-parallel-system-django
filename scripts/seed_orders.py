import os
import sys
import django
from pathlib import Path
from random import Random
from django.utils import timezone
import datetime

# Configure stdout/stderr to use UTF-8 to safely handle emojis on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Setup Django environment
sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")
django.setup()

from store.models import Order, OrderItem, Product, User

def main():
    random = Random(42)
    users = list(User.objects.all()[:100])
    products = list(Product.objects.filter(stock_quantity__gt=5)[:50])
    
    if not users:
        print("️ No users found in database! Please run `python scripts/seed.py` first to populate users.")
        return
    if not products:
        print("️ No products found in database! Please run `python scripts/seed.py` first to populate products.")
        return
        
    print(f" Starting Order Seeder...")
    print(f"   Found {len(users)} users and {len(products)} products available for ordering.")
    
    orders_created = 0
    items_created = 0
    
    # We will generate 150 random orders spread across today and yesterday
    for i in range(150000):
        user = random.choice(users)
        num_items = random.randint(1, 4)
        selected_products = random.sample(products, num_items)
        
        # Create Order (initially pending with total_price=0.0)
        order = Order(
            user=user,
            total_price=0.0,
            status=random.choice(["completed", "completed", "completed", "pending"]), 
        )
        order.save()
        
        total_price = 0.0
        for prod in selected_products:
            qty = random.randint(1, 3)
            unit_price = float(prod.price)
            subtotal = qty * unit_price
            total_price += subtotal
            
            OrderItem.objects.create(
                order=order,
                product=prod,
                quantity=qty,
                unit_price=unit_price,
                subtotal=subtotal
            )
            items_created += 1
            
        # Update Order's total price
        order.total_price = round(total_price, 2)
        order.save()
        
        # Set a realistic created_at timestamp spanning today or yesterday
        days_ago = random.choice([0, 1])
        random_hour = random.randint(0, 23)
        random_minute = random.randint(0, 59)
        target_date = timezone.now() - datetime.timedelta(days=days_ago, hours=random_hour, minutes=random_minute)
        
        # Force update using .update() to bypass auto_now_add restriction
        Order.objects.filter(id=order.id).update(created_at=target_date)
        OrderItem.objects.filter(order_id=order.id).update(created_at=target_date)
        
        orders_created += 1
        
    print(f" Seeding complete!")
    print(f"   Successfully generated {orders_created} Orders and {items_created} Order Items!")
    print(f"   Orders are realistically distributed over today and yesterday.")

if __name__ == "__main__":
    main()
