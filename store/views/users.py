from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from store.models import User
from store.serializers import UserSerializer
from store.views.pagination import get_pagination_params


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSerializer
    lookup_url_kwarg = "user_id"

    def get_queryset(self) -> QuerySet[User]:
        return User.objects.order_by("id")

    def list(self, request, *args, **kwargs):
        skip, limit = get_pagination_params(request)
        queryset = self.get_queryset()[skip : skip + limit]
        return Response(self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        try:
            user = User.objects.get(pk=kwargs["user_id"])
        except User.DoesNotExist as exc:
            raise NotFound("User not found") from exc
        return Response(self.get_serializer(user).data)
