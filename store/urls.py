from django.urls import path

from store.views import (
    CartItemDetailView,
    CartItemsView,
    CartView,
    OrderViewSet,
    ProductViewSet,
    UserOrdersView,
    UserViewSet,
)


user_list = UserViewSet.as_view({"get": "list"})
user_detail = UserViewSet.as_view({"get": "retrieve"})
product_list = ProductViewSet.as_view({"get": "list"})
product_detail = ProductViewSet.as_view({"get": "retrieve"})
order_list = OrderViewSet.as_view({"get": "list"})
order_detail = OrderViewSet.as_view({"get": "retrieve"})
order_checkout = OrderViewSet.as_view({"post": "checkout"})


urlpatterns = [
    path("users", user_list, name="user-list"),
    path("users/<int:user_id>", user_detail, name="user-detail"),
    path("products", product_list, name="product-list"),
    path("products/<int:product_id>", product_detail, name="product-detail"),
    path("cart/items", CartItemsView.as_view(), name="cart-items"),
    path(
        "cart/items/<int:cart_item_id>",
        CartItemDetailView.as_view(),
        name="cart-item-detail",
    ),
    path("cart/<int:user_id>", CartView.as_view(), name="cart-detail"),
    path("orders/checkout", order_checkout, name="order-checkout"),
    path("orders", order_list, name="order-list"),
    path("orders/user/<int:user_id>", UserOrdersView.as_view(), name="user-orders"),
    path("orders/<int:order_id>", order_detail, name="order-detail"),
]
