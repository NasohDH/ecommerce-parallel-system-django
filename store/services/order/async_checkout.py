from decimal import Decimal
from celery import shared_task
from django.db import transaction

from store.models import Cart, CartItem, Order, OrderItem, Product, User
from store.services.notification import send_notification
from store.services.payment import process_payment
import logging

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    acks_late=True,                 # Don't delete from queue until completely successful
)
def process_checkout_task(self, order_id: int, user_id: int):
    try:
        with transaction.atomic():
            # Use select_for_update to lock the order row during checks
            order = Order.objects.select_for_update().get(pk=order_id)
            
            # IDEMPOTENCY CHECK: If this message was delivered twice, skip it!
            if order.status != "pending":
                logger.info(f"Order {order_id} already processed (status: {order.status}). Skipping duplicate message.")
                return
            
            # Re-fetch cart with lock
            cart = Cart.objects.select_for_update().filter(user_id=user_id).first()
            if not cart:
                raise ValueError("Cart is empty")

            cart_items = list(
                CartItem.objects.filter(cart=cart)
                .select_related("product")
                .order_by("product_id")
            )
            if not cart_items:
                raise ValueError("Cart is empty")

            product_ids = [item.product_id for item in cart_items]
            products_by_id = {
                product.id: product
                for product in Product.objects.select_for_update()
                .filter(pk__in=product_ids)
                .order_by("id")
            }

            total_price = Decimal("0.00")
            order_items_data = []

            for cart_item in cart_items:
                product = products_by_id.get(cart_item.product_id)
                if not product:
                    raise ValueError(f"Product {cart_item.product_id} not found")

                if product.stock_quantity < cart_item.quantity:
                    raise ValueError(f"Not enough stock for product {cart_item.product_id}")

                unit_price = Decimal(str(product.price))
                subtotal = unit_price * cart_item.quantity
                total_price += subtotal
                order_items_data.append((cart_item, product, unit_price, subtotal))

            # Process payment (this locks the User)
            process_payment(user_id=user_id, total_cart_price=total_price)

            # Update Order
            order.total_price = float(total_price)
            order.status = "completed"
            order.save(update_fields=["total_price", "status"])

            # Create OrderItems and Update Stock
            for cart_item, product, unit_price, subtotal in order_items_data:
                product.stock_quantity -= cart_item.quantity
                product.save(update_fields=["stock_quantity"])
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=cart_item.quantity,
                    unit_price=float(unit_price),
                    subtotal=float(subtotal),
                )

            # Clear Cart
            CartItem.objects.filter(cart=cart).delete()

            # Trigger notification
            transaction.on_commit(
                lambda: send_notification.delay(
                    event="order_checkout",
                    order_id=order.id,
                    user_id=user_id,
                    total_price=str(total_price),
                )
            )

    except ValueError as e:
        # Business logic failure (out of stock, empty cart, insufficient funds).
        # We catch this cleanly, mark the order as failed, and do NOT retry.
        Order.objects.filter(pk=order_id).update(status="failed")
        return
    except Exception as e:
        # Unexpected system failure (e.g., Database is down).
        # We manually retry to handle final failure logging.
        try:
            # Wait 1s, then 2s, then 4s (backoff)
            backoff_delay = 2 ** self.request.retries 
            # Send to the back of the queue by scheduling in the future
            self.retry(exc=e, countdown=backoff_delay, max_retries=3)
        except self.MaxRetriesExceededError:
            # FINAL FAILURE AFTER ALL TRIES
            logger.error(f"CRITICAL: Order {order_id} failed completely after 3 retries. Error: {e}")
            Order.objects.filter(pk=order_id).update(status="failed")

