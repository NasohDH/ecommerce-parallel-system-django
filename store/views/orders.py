from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from store import services
from store.models import Order
from store.serializers import CheckoutSerializer, OrderSerializer
from store.views.pagination import get_pagination_params


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    lookup_url_kwarg = "order_id"

    def get_queryset(self) -> QuerySet[Order]:
        return Order.objects.prefetch_related("items").order_by("-created_at")

    def list(self, request, *args, **kwargs):
        skip, limit = get_pagination_params(request)
        queryset = self.get_queryset()
        user_id = request.query_params.get("user_id")
        if user_id is not None:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except (TypeError, ValueError) as exc:
                raise ValidationError("user_id must be an integer") from exc
        queryset = queryset[skip : skip + limit]
        return Response(self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        try:
            order = self.get_queryset().get(pk=kwargs["order_id"])
        except Order.DoesNotExist as exc:
            raise NotFound("Order not found") from exc
        return Response(self.get_serializer(order).data)

    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # order = services.checkout_queue.checkout(serializer.validated_data["user_id"])
        from store.services.order.order_checkout import checkout_cart
        order = checkout_cart(serializer.validated_data["user_id"])
        return Response(
            self.get_serializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class UserOrdersView(APIView):
    def get(self, request, user_id: int):
        skip, limit = get_pagination_params(request)
        queryset = (
            Order.objects.prefetch_related("items")
            .filter(user_id=user_id)
            .order_by("-created_at")
        )[skip : skip + limit]
        return Response(OrderSerializer(queryset, many=True).data)
