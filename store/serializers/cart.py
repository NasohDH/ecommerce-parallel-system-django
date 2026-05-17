from rest_framework import serializers

from store.models import Cart, CartItem
from store.serializers.product import ProductSerializer


class AddCartItemSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField()


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField()


class CartItemSerializer(serializers.ModelSerializer):
    cart_id = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(read_only=True)
    product = ProductSerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "cart_id",
            "product_id",
            "quantity",
            "created_at",
            "product",
        ]


class CartSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "user_id", "created_at", "items"]


class EmptyCartSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    user_id = serializers.IntegerField()
    created_at = serializers.DateTimeField(allow_null=True)
    items = CartItemSerializer(many=True)
