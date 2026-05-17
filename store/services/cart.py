from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import NotFound

from store.models import Cart, CartItem
from store.services.errors import BadRequest
from store.services.product import get_product_or_404
from store.services.user import get_user_or_404


def empty_cart_response(user_id: int) -> dict:
    return {
        "id": None,
        "user_id": user_id,
        "created_at": None,
        "items": [],
    }


def get_user_cart(user_id: int) -> Cart | dict:
    get_user_or_404(user_id)
    cart = (
        Cart.objects.prefetch_related("items__product")
        .filter(user_id=user_id)
        .first()
    )
    if not cart:
        return empty_cart_response(user_id)
    return cart


def add_item_to_cart(user_id: int, product_id: int, quantity: int) -> Cart:
    if quantity <= 0:
        raise BadRequest("Quantity must be greater than zero")

    get_user_or_404(user_id)
    get_product_or_404(product_id)

    with transaction.atomic():
        cart, _ = Cart.objects.get_or_create(user_id=user_id)
        cart_item = CartItem.objects.filter(
            cart=cart,
            product_id=product_id,
        ).first()
        if cart_item:
            cart_item.quantity += quantity
            cart_item.save(update_fields=["quantity"])
        else:
            CartItem.objects.create(
                cart=cart,
                product_id=product_id,
                quantity=quantity,
            )

    return (
        Cart.objects.prefetch_related("items__product")
        .get(user_id=user_id)
    )


def update_cart_item(cart_item_id: int, quantity: int) -> CartItem:
    if quantity <= 0:
        raise BadRequest("Quantity must be greater than zero")

    try:
        cart_item = CartItem.objects.select_related("cart", "product").get(
            pk=cart_item_id
        )
    except CartItem.DoesNotExist as exc:
        raise NotFound("Cart item not found") from exc

    cart_item.quantity = quantity
    cart_item.save(update_fields=["quantity"])
    return cart_item


def delete_cart_item(cart_item_id: int) -> dict[str, str]:
    try:
        cart_item = CartItem.objects.get(pk=cart_item_id)
    except CartItem.DoesNotExist as exc:
        raise NotFound("Cart item not found") from exc

    cart_item.delete()
    return {"message": "Cart item deleted successfully"}
