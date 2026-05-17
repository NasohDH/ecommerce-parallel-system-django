from rest_framework.exceptions import NotFound

from store.models import Product


def get_product_or_404(product_id: int) -> Product:
    try:
        return Product.objects.get(pk=product_id)
    except Product.DoesNotExist as exc:
        raise NotFound("Product not found") from exc
