import os
import sys
from pathlib import Path
from random import Random

# Minimal changes to work with Django
sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")

import django
django.setup()

from store.models import Product, User


TARGET_PRODUCTS = 2_000
TARGET_USERS = 50_000
BATCH_SIZE = 5_000

PASSWORD_HASH = "seeded_password_hash"
HIGH_STOCK_QUANTITY = 20_000

PRODUCT_CATEGORIES = [
    "Laptop", "Phone", "Headphones", "Keyboard", "Mouse", "Monitor",
    "Camera", "Speaker", "Tablet", "Smartwatch", "Backpack", "Chair",
    "Desk", "Printer", "Router", "Microphone",
]

PRODUCT_ADJECTIVES = [
    "Classic", "Premium", "Compact", "Wireless", "Smart", "Portable",
    "Eco", "Pro", "Essential", "Advanced", "Durable", "Modern",
]


def count_rows(session, model) -> int:
    return model.objects.count()


def max_id(session, model) -> int:
    obj = model.objects.order_by("-id").first()
    return obj.id if obj else 0


def ensure_high_stock_product(session) -> None:
    high_stock_product = Product.objects.filter(stock_quantity=HIGH_STOCK_QUANTITY).first()
    if high_stock_product:
        return

    product = Product.objects.order_by("id").first()
    if product:
        product.stock_quantity = HIGH_STOCK_QUANTITY
        product.save(update_fields=["stock_quantity"])
        print(f"Updated product {product.id} stock to {HIGH_STOCK_QUANTITY}")


def seed_products(session) -> None:
    existing_count = count_rows(session, Product)
    remaining = max(TARGET_PRODUCTS - existing_count, 0)
    start_id = max_id(session, Product) + 1
    random = Random(2026)

    for batch_start in range(0, remaining, BATCH_SIZE):
        batch_size = min(BATCH_SIZE, remaining - batch_start)
        products = []

        for offset in range(batch_size):
            product_number = start_id + batch_start + offset
            category = PRODUCT_CATEGORIES[product_number % len(PRODUCT_CATEGORIES)]
            adjective = PRODUCT_ADJECTIVES[product_number % len(PRODUCT_ADJECTIVES)]

            products.append(
                Product(
                    name=f"{adjective} {category} {product_number}",
                    description=(
                        f"Reliable {category.lower()} for everyday e-commerce "
                        "testing and catalog browsing."
                    ),
                    price=round(random.uniform(9.99, 1499.99), 2),
                    stock_quantity=random.randint(20, 250),
                    image_url=f"https://picsum.photos/seed/product-{product_number}/600/600",
                )
            )

        Product.objects.bulk_create(products, batch_size=BATCH_SIZE)
        print(f"Seeded {batch_start + batch_size}/{remaining} new products")

    ensure_high_stock_product(session)


def seed_users(session) -> None:
    existing_count = count_rows(session, User)
    remaining = max(TARGET_USERS - existing_count, 0)
    start_id = max_id(session, User) + 1

    for batch_start in range(0, remaining, BATCH_SIZE):
        batch_size = min(BATCH_SIZE, remaining - batch_start)
        users = []

        for offset in range(batch_size):
            user_number = start_id + batch_start + offset
            users.append(
                User(
                    email=f"user{user_number}@example.com",
                    username=f"user{user_number}",
                    hashed_password=PASSWORD_HASH,
                )
            )

        User.objects.bulk_create(users, batch_size=BATCH_SIZE)
        print(f"Seeded {batch_start + batch_size}/{remaining} new users")


def main() -> None:
    # We pass None for session as we use Django ORM globally
    seed_products(None)
    seed_users(None)

    product_count = count_rows(None, Product)
    user_count = count_rows(None, User)

    print(f"Products: {product_count}")
    print(f"Users: {user_count}")
    print("Carts and cart items were left empty.")


if __name__ == "__main__":
    main()
