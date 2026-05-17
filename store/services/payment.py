from decimal import Decimal
from time import sleep

from rest_framework.exceptions import NotFound

from store.models import User
from store.services.errors import BadRequest


def process_payment(user_id: int, total_cart_price: Decimal) -> User:
    try:
        user = User.objects.select_for_update().get(pk=user_id)
    except User.DoesNotExist as exc:
        raise NotFound("User not found") from exc

    sleep(1)
    if user.balance < total_cart_price:
        raise BadRequest("no enough money")

    user.balance -= total_cart_price
    user.save(update_fields=["balance"])
    return user
