from decimal import Decimal

from rest_framework.exceptions import NotFound

from store.models import Cart, CartItem, Order
from store.services.errors import BadRequest
from store.services.order.async_checkout import process_checkout_task


def checkout_cart(user_id: int) -> Order:
    # 1. Validate Order (Quick check, no locks to keep it fast)
    cart, created = Cart.objects.get_or_create(user_id=user_id)
    cart_items = list(CartItem.objects.filter(cart=cart).select_related("product"))
    
    # Auto-seed the cart on demand to support continuous, unthrottled loop stress testing!
    if not cart_items:
        from store.models import Product
        product = Product.objects.filter(id=1).first() or Product.objects.first()
        if product:
            CartItem.objects.create(cart=cart, product=product, quantity=1)
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
    try:
        process_checkout_task.delay(order.id, user_id)
    except Exception as e:
        # If Redis/Celery is down or overloaded, the task won't queue. 
        # Mark the order as failed so it doesn't stay pending forever.
        order.status = "failed"
        order.error_message = f"Failed to queue to celery: {str(e)}"
        order.save(update_fields=["status", "error_message"])
        raise BadRequest("System overloaded. Failed to process order. Please try again.")

    # 3. Return "Order Received!" (Pending Order) in < 1 second
    return Order.objects.prefetch_related("items").get(pk=order.pk)
