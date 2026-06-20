from decimal import Decimal
from celery import shared_task
from django.db import transaction

from store.models import Cart, CartItem, Order, OrderItem, Product, User
from store.services.notification import send_notification
from store.services.payment import process_payment
from store.services.errors import BadRequest
from rest_framework.exceptions import NotFound
import logging

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    acks_late=True,                 
)
def process_checkout_task(self, order_id: int, user_id: int):
    try:
        with transaction.atomic():
            
            order = Order.objects.select_for_update().get(pk=order_id)
            
            
            if order.status != "pending":
                logger.info(f"Order {order_id} already processed (status: {order.status}). Skipping duplicate message.")
                return
            
            
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

            
            process_payment(user_id=user_id, total_cart_price=total_price)

            
            order.total_price = float(total_price)
            order.status = "completed"
            order.save(update_fields=["total_price", "status"])

            
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

            
            CartItem.objects.filter(cart=cart).delete()

            
            transaction.on_commit(
                lambda: send_notification.delay(
                    event="order_checkout",
                    order_id=order.id,
                    user_id=user_id,
                    total_price=str(total_price),
                )
            )

    except Order.DoesNotExist:
        
        logger.warning(f"Order {order_id} does not exist. Skipping.")
        return
    except (ValueError, BadRequest, NotFound) as e:
        
        
        Order.objects.filter(pk=order_id).update(status="failed", error_message=str(e))
        return
    except Exception as e:
        
        err_msg = str(e).lower()
        if "money" in err_msg or "balance" in err_msg or "stock" in err_msg or "empty" in err_msg or "exist" in err_msg:
            logger.warning(f"Non-retriable failure for Order {order_id}: {e}")
            Order.objects.filter(pk=order_id).update(status="failed", error_message=str(e))
            return

        
        
        try:
            
            backoff_delay = 2 ** self.request.retries 
            
            self.retry(exc=e, countdown=backoff_delay, max_retries=3)
        except self.MaxRetriesExceededError:
            
            logger.error(f"CRITICAL: Order {order_id} failed completely after 3 retries. Error: {e}")
            Order.objects.filter(pk=order_id).update(status="failed", error_message=str(e))

