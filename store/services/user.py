from rest_framework.exceptions import NotFound

from store.models import User


def get_user_or_404(user_id: int) -> User:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise NotFound("User not found") from exc
