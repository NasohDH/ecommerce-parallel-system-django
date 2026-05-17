from decimal import Decimal

from rest_framework.exceptions import NotFound

from store.models import Cart, CartItem, Order
from store.services.errors import BadRequest
from store.services.order.async_checkout import process_checkout_task


def checkout_cart(user_id: int) -> Order:
    # 1. Validate Order (Quick check, no locks to keep it fast)
    cart = Cart.objects.filter(user_id=user_id).first()
    if not cart:
        raise BadRequest("Cart is empty")

    cart_items = list(CartItem.objects.filter(cart=cart).select_related("product"))
    if not cart_items:
        raise BadRequest("Cart is empty")

    # Estimate total price for the pending order display
    total_price = sum(Decimal(str(item.product.price)) * item.quantity for item in cart_items)

    # Create the Order immediately in "pending" status
    order = Order.objects.create(
        user_id=user_id,
        total_price=float(total_price),
        status="pending",
    )

    # 2. Send to Messaging Queue (Celery)
    process_checkout_task.delay(order.id, user_id)

    # 3. Return "Order Received!" (Pending Order) in < 1 second
    return Order.objects.prefetch_related("items").get(pk=order.pk)
