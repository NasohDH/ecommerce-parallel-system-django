import os
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")

import django


PRODUCT_ID = 1
QUANTITY = 1
BATCH_SIZE = 5_000


def seed_carts() -> tuple[int, int, int]:
    from store.models import Cart, CartItem, Product, User

    if not Product.objects.filter(pk=PRODUCT_ID).exists():
        raise RuntimeError(f"Product {PRODUCT_ID} does not exist")

    user_ids = list(User.objects.order_by("id").values_list("id", flat=True))
    carts_created = 0
    items_created = 0
    items_updated = 0

    for batch_start in range(0, len(user_ids), BATCH_SIZE):
        batch_user_ids = user_ids[batch_start : batch_start + BATCH_SIZE]

        existing_carts = {
            cart.user_id: cart
            for cart in Cart.objects.filter(user_id__in=batch_user_ids)
        }

        missing_user_ids = [
            user_id for user_id in batch_user_ids if user_id not in existing_carts
        ]
        Cart.objects.bulk_create(
            [Cart(user_id=user_id) for user_id in missing_user_ids],
            batch_size=BATCH_SIZE,
        )
        carts_created += len(missing_user_ids)

        carts = {
            cart.user_id: cart
            for cart in Cart.objects.filter(user_id__in=batch_user_ids)
        }
        cart_ids = [cart.id for cart in carts.values()]
        existing_items = {
            item.cart_id: item
            for item in CartItem.objects.filter(
                cart_id__in=cart_ids,
                product_id=PRODUCT_ID,
            )
        }

        items_to_create = []
        items_to_update = []

        for cart in carts.values():
            cart_item = existing_items.get(cart.id)
            if cart_item:
                if cart_item.quantity != QUANTITY:
                    cart_item.quantity = QUANTITY
                    items_to_update.append(cart_item)
                else:
                    items_updated += 1
            else:
                items_to_create.append(
                    CartItem(
                        cart_id=cart.id,
                        product_id=PRODUCT_ID,
                        quantity=QUANTITY,
                    )
                )

        CartItem.objects.bulk_create(items_to_create, batch_size=BATCH_SIZE)
        CartItem.objects.bulk_update(
            items_to_update,
            ["quantity"],
            batch_size=BATCH_SIZE,
        )

        items_created += len(items_to_create)
        items_updated += len(items_to_update)

        processed = min(batch_start + BATCH_SIZE, len(user_ids))
        print(f"Processed {processed}/{len(user_ids)} users")

    return carts_created, items_created, items_updated


def main() -> None:
    django.setup()
    carts_created, items_created, items_updated = seed_carts()

    print(f"Carts created: {carts_created}")
    print(f"Cart items created: {items_created}")
    print(f"Cart items updated or already present: {items_updated}")
    print(f"Product id: {PRODUCT_ID}")
    print(f"Quantity per cart: {QUANTITY}")


if __name__ == "__main__":
    main()
