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
        from store.services.order.order_checkout import checkout_cart
        order = checkout_cart(serializer.validated_data["user_id"])
        return Response(
            self.get_serializer(order).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="trigger-batch")
    def trigger_batch(self, request):
        custom_date = request.data.get("date") or request.query_params.get("date")
        
        from store.services.sales.batch_processing import trigger_daily_sales_batch
        from store.models.sales_report import DailySalesReport
        import time
        
        start_time = time.perf_counter()
        
        # Trigger daily sales batch synchronously to utilize dynamic in-process code and bypass Celery caching
        report_id = trigger_daily_sales_batch(custom_date=custom_date)
        
        if report_id is None:
            return Response({
                "message": "Daily sales batch job is already running or was skipped."
            }, status=status.HTTP_409_CONFLICT)
        
        # Keep HTTP request open: Poll the database until completion
        while True:
            report = DailySalesReport.objects.get(pk=report_id)
            if report.status == "completed":
                break
            elif report.status == "failed":
                return Response({
                    "error": "Daily sales batch job failed!",
                    "report_id": report_id
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            time.sleep(0.2)
            
        elapsed = time.perf_counter() - start_time
        return Response({
            "message": "Daily sales batch job completed successfully!",
            "report_id": report_id,
            "target_date": custom_date or "yesterday (default)",
            "request_elapsed_seconds": round(elapsed, 3),
            "total_execution_time_seconds": report.total_execution_time,
            "pdf_generation_time_seconds": report.pdf_generation_time
        }, status=status.HTTP_200_OK)


class UserOrdersView(APIView):
    def get(self, request, user_id: int):
        skip, limit = get_pagination_params(request)
        queryset = (
            Order.objects.prefetch_related("items")
            .filter(user_id=user_id)
            .order_by("-created_at")
        )[skip : skip + limit]
        return Response(OrderSerializer(queryset, many=True).data)
