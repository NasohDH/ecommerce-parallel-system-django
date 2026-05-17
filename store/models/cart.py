from django.db import models

from store.models.product import Product
from store.models.user import User


class Cart(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        models.DO_NOTHING,
        db_column="user_id",
        related_name="cart",
    )
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)

    class Meta:
        managed = False
        db_table = "carts"


class CartItem(models.Model):
    id = models.AutoField(primary_key=True)
    cart = models.ForeignKey(
        Cart,
        models.DO_NOTHING,
        db_column="cart_id",
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        models.DO_NOTHING,
        db_column="product_id",
        related_name="cart_items",
    )
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(blank=True, null=True, auto_now_add=True)

    class Meta:
        managed = False
        db_table = "cart_items"
