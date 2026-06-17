import time
from django.core.cache import cache
from django.db.models import QuerySet
from rest_framework import viewsets, mixins, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from store.models import Product
from store.serializers import ProductSerializer
from store.views.pagination import get_pagination_params


class ProductViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    lookup_url_kwarg = "product_id"

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return response

    def get_queryset(self) -> QuerySet[Product]:
        return Product.objects.order_by("id")

    def _get_or_rebuild_cache(self, cache_key, fetch_func):
        cached_payload = cache.get(cache_key)
        
        if cached_payload is not None:
            if isinstance(cached_payload, tuple) and len(cached_payload) == 2:
                data, expires_at = cached_payload
                if time.time() < expires_at:
                    return Response(data)
            else:
                data = cached_payload
            
            lock = cache.lock(f"{cache_key}_lock", timeout=10)
            if lock.acquire(blocking=False):
                try:
                    data = fetch_func()
                    cache.set(cache_key, (data, time.time() + 60), timeout=7200)
                    return Response(data)
                finally:
                    try:
                        lock.release()
                    except Exception:
                        pass
            else:
                return Response(data)
        else:
            lock = cache.lock(f"{cache_key}_lock", timeout=10)
            if lock.acquire(blocking=False):
                try:
                    data = fetch_func()
                    cache.set(cache_key, (data, time.time() + 60), timeout=7200)
                    return Response(data)
                finally:
                    try:
                        lock.release()
                    except Exception:
                        pass
            else:
                return Response({"error": "Server busy building cache, please try again in 10 seconds"}, status=200)

    def list(self, request, *args, **kwargs):
        skip, limit = get_pagination_params(request)
        cache_key = f"products_list_{skip}_{limit}"
        
        def fetch_list():
            queryset = self.get_queryset()[skip : skip + limit]
            return self.get_serializer(queryset, many=True).data
            
        return self._get_or_rebuild_cache(cache_key, fetch_list)

    def retrieve(self, request, *args, **kwargs):
        product_id = kwargs["product_id"]
        cache_key = f"product_detail_{product_id}"
        
        def fetch_detail():
            try:
                product = Product.objects.get(pk=product_id)
            except Product.DoesNotExist as exc:
                raise NotFound("Product not found") from exc
            return self.get_serializer(product).data
            
        return self._get_or_rebuild_cache(cache_key, fetch_detail)
