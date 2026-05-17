from rest_framework import serializers

from store.models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_id",
            "quantity",
            "unit_price",
            "subtotal",
            "created_at",
        ]


class OrderSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "user_id", "total_price", "status", "created_at", "items"]


class CheckoutSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
