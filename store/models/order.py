from django.db import models

from store.models.product import Product
from store.models.user import User


class Order(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        models.DO_NOTHING,
        db_column="user_id",
        related_name="orders",
    )
    total_price = models.FloatField()
    status = models.CharField(max_length=50, default="pending")
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)

    class Meta:
        managed = False
        db_table = "orders"


class OrderItem(models.Model):
    id = models.AutoField(primary_key=True)
    order = models.ForeignKey(
        Order,
        models.DO_NOTHING,
        db_column="order_id",
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        models.DO_NOTHING,
        db_column="product_id",
        related_name="order_items",
    )
    quantity = models.IntegerField()
    unit_price = models.FloatField()
    subtotal = models.FloatField()
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)

    class Meta:
        managed = False
        db_table = "order_items"
