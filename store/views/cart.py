from rest_framework.response import Response
from rest_framework.views import APIView

from store import services
from store.serializers import (
    AddCartItemSerializer,
    CartItemSerializer,
    CartSerializer,
    EmptyCartSerializer,
    UpdateCartItemSerializer,
)


class CartView(APIView):
    def get(self, request, user_id: int):
        cart = services.get_user_cart(user_id)
        if isinstance(cart, dict):
            return Response(EmptyCartSerializer(cart).data)
        return Response(CartSerializer(cart).data)


class CartItemsView(APIView):
    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = services.add_item_to_cart(**serializer.validated_data)
        return Response(CartSerializer(cart).data)


