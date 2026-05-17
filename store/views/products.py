from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from store.models import Product
from store.serializers import ProductSerializer
from store.views.pagination import get_pagination_params


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    lookup_url_kwarg = "product_id"

    def get_queryset(self) -> QuerySet[Product]:
        return Product.objects.order_by("id")

    def list(self, request, *args, **kwargs):
        skip, limit = get_pagination_params(request)
        queryset = self.get_queryset()[skip : skip + limit]
        return Response(self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        try:
            product = Product.objects.get(pk=kwargs["product_id"])
        except Product.DoesNotExist as exc:
            raise NotFound("Product not found") from exc
        return Response(self.get_serializer(product).data)
