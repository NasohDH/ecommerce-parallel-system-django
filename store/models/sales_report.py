from django.db import models
from django.utils import timezone

class DailySalesReport(models.Model):
    date = models.DateField(unique=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("finalizing", "Finalizing"),  
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="pending"
    )
    total_orders = models.IntegerField(default=0)
    processed_orders = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    pdf_report_path = models.CharField(max_length=500, blank=True, null=True)
    pdf_generation_time = models.FloatField(default=0.0)
    total_execution_time = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_sales_reports"
        managed = True


class SalesProcessingChunk(models.Model):
    report = models.ForeignKey(DailySalesReport, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField()
    order_ids = models.JSONField(default=list)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed")
        ],
        default="pending"
    )
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    processed_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "sales_processing_chunks"
        managed = True


class DeadLetterSales(models.Model):
    report = models.ForeignKey(DailySalesReport, on_delete=models.CASCADE, related_name="dead_letters")
    order_id = models.IntegerField()
    error_reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        db_table = "dead_letter_sales"
        managed = True
