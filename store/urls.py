from django.urls import path

from store.views import (
    CartItemsView,
    CartView,
    OrderViewSet,
    ProductViewSet,
    UserViewSet,
)


user_list = UserViewSet.as_view({"get": "list"})
user_detail = UserViewSet.as_view({"get": "retrieve"})
product_list = ProductViewSet.as_view({"get": "list", "post": "create"})
product_detail = ProductViewSet.as_view({"get": "retrieve"})
order_checkout = OrderViewSet.as_view({"post": "checkout"})
order_trigger_batch = OrderViewSet.as_view({"post": "trigger_batch"})


urlpatterns = [
    path("users", user_list, name="user-list"),
    path("users/<int:user_id>", user_detail, name="user-detail"),
    path("products", product_list, name="product-list"),
    path("products/<int:product_id>", product_detail, name="product-detail"),
    path("cart/items", CartItemsView.as_view(), name="cart-items"),
    path("cart/<int:user_id>", CartView.as_view(), name="cart-detail"),
    path("orders/checkout", order_checkout, name="order-checkout"),
    path("orders/trigger-batch", order_trigger_batch, name="order-trigger-batch"),
]
