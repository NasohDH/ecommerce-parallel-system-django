import logging
import math
from datetime import timedelta
from decimal import Decimal

from celery import shared_task, chord
from django.db import transaction, models
from django.utils import timezone
from django.conf import settings

from store.models import Order, DailySalesReport, SalesProcessingChunk, DeadLetterSales

logger = logging.getLogger(__name__)


def _check_and_trigger_finalize(report_id: int) -> None:
    """
    Check whether every chunk for this report is finished (completed OR failed).
    If so, atomically transition the report from "processing" → "finalizing" using
    a single conditional UPDATE — only the one task that wins this compare-and-swap
    will schedule finalize_sales_batch, eliminating the duplicate-PDF race condition.
    """
    remaining = SalesProcessingChunk.objects.filter(
        report_id=report_id
    ).exclude(status__in=["completed", "failed"]).count()

    if remaining > 0:
        return  # Other chunks are still running

    # Atomic CAS: filter(status="processing") ensures only ONE concurrent caller
    # succeeds. Django UPDATE returns the number of rows actually modified.
    claimed = DailySalesReport.objects.filter(
        pk=report_id,
        status="processing"
    ).update(status="finalizing")

    if claimed:
        logger.info(f"All chunks done for report {report_id}. Triggering finalizer (claimed).")
        finalize_sales_batch.delay([], report_id)


@shared_task
def trigger_daily_sales_batch(custom_date=None, *args, **kwargs):
    """
    Master Task: Partitioning & Distribution
    Runs every day at midnight. Gathers orders for the target date and chunks them.
    """
    from django.core.cache import cache
    
    if custom_date:
        from datetime import datetime
        target_date = datetime.strptime(custom_date, '%Y-%m-%d').date()
    else:
        target_date = timezone.now().date() - timedelta(days=1)
    
    # Distributed Cron Lock to prevent duplicate executions from 3 apps
    lock = cache.lock(f"daily_batch_lock_{target_date}", timeout=7200)
    if not lock.acquire(blocking=False):
        logger.info(f"Daily sales batch for {target_date} is already running elsewhere. Exiting.")
        return
        
    try:
        # Check if a report already exists to prevent duplicate runs (Idempotency)
        report, created = DailySalesReport.objects.get_or_create(
            date=target_date,
            defaults={"status": "processing"}
        )
    
        if not created and report.status == "completed" and not custom_date:
            logger.info(f"Report for {target_date} already completed. Skipping.")
            return report.id
    
        # Get all completed orders for THAT SPECIFIC date
        orders_qs = Order.objects.filter(status="completed", created_at__date=target_date).order_by("id")
        total_orders = orders_qs.count()
    
        report.total_orders = total_orders
        report.status = "processing"
        report.save(update_fields=["total_orders", "status"])
    
        if total_orders == 0:
            logger.info(f"No orders to process for {target_date}.")
            report.status = "completed"
            report.save(update_fields=["status"])
            # We could still generate an empty PDF here, but we'll skip for now.
            return report.id
    
        # Recovery Logic: Check if we are resuming an existing run
        existing_chunks = report.chunks.all()
    
        if existing_chunks.exists():
            logger.info(f"Found existing chunks for report {report.id}. Resuming incomplete work...")
            chunk_tasks = []
            for chunk in existing_chunks:
                if chunk.status != "completed":
                    # Reset status to pending before retrying
                    chunk.status = "pending"
                    chunk.save(update_fields=["status"])
                    chunk_tasks.append(process_sales_chunk.s(chunk.id))
    
            if not chunk_tasks:
                logger.info("All existing chunks are already completed. Triggering finalizer just in case.")
                finalize_sales_batch.delay([], report.id)
                return report.id
    
            logger.info(f"Resuming {len(chunk_tasks)} incomplete chunks...")
            from celery import group
            group(chunk_tasks).apply_async()
            return report.id
    
        # 1. Partitioning (Fresh Run): Determine optimal chunk size based on idle capacity
        import requests
        try:
            response = requests.get("http://127.0.0.1:8080/system/local-metrics", timeout=2)
            metrics = response.json()
            busy_threads = metrics["system"]["thread_pool"]["running_threads"]
        except Exception as e:
            logger.warning(f"Could not reach web server for metrics, defaulting to 0 busy: {e}")
            busy_threads = 0
    
        total_workers = getattr(settings, "SYSTEM_MAX_WORKERS", 20)
        # Ensure idle_threads is at least 4 to prevent dropping to 1 chunk under high load/thread leaks
        idle_threads = max(4, total_workers - busy_threads)
        # Cap idle_threads at 20 to target exactly 20 chunks when system is fully idle
        idle_threads = min(20, idle_threads)
        chunk_size = math.ceil(total_orders / idle_threads)
        chunk_size = max(50, chunk_size)
        # Safety Cap: Max 1000 orders per chunk to guarantee parallel execution in Celery
        chunk_size = min(chunk_size, 1000) 
    
        order_ids = list(orders_qs.values_list("id", flat=True))
        chunk_tasks = []
    
        for i in range(0, total_orders, chunk_size):
            chunk_ids = order_ids[i:i + chunk_size]
            chunk = SalesProcessingChunk.objects.create(
                report=report,
                chunk_index=i // chunk_size,
                order_ids=chunk_ids,
                status="pending"
            )
            chunk_tasks.append(process_sales_chunk.s(chunk.id))
    
        logger.info(f"Dispatched {len(chunk_tasks)} fresh chunks for {total_orders} orders.")
    
        # 3. Execute in parallel
        from celery import group
        group(chunk_tasks).apply_async()
    
        return report.id
    
    finally:
        try:
            lock.release()
        except Exception:
            pass


@shared_task(bind=True, acks_late=True, max_retries=3)
def process_sales_chunk(self, chunk_id: int):
    """
    Worker Task: Execution & Skip on failure.
    Processes a specific chunk of orders, calculates revenue, handles dead letters.

    On transient infrastructure failure (e.g. DB timeout) the task retries up to 3
    times with exponential backoff.  On permanent failure it marks the chunk "failed"
    and calls _check_and_trigger_finalize so the report is never left stuck in
    "processing" forever.
    """
    try:
        chunk = SalesProcessingChunk.objects.select_related('report').get(pk=chunk_id)
        report = chunk.report

        # Idempotency at chunk level: don't re-run completed chunks
        if chunk.status == "completed":
            return {"chunk_id": chunk_id, "status": "already_completed"}

        chunk.status = "processing"
        chunk.save(update_fields=["status"])

        chunk_revenue = Decimal("0.00")
        success_count = 0

        # IDEMPOTENCY: Skip orders that were already processed in a previous attempt
        all_order_ids = chunk.order_ids
        processed_count_before = chunk.processed_count
        orders_to_process = all_order_ids[processed_count_before:]

        if not orders_to_process:
            logger.info(f"Chunk {chunk_id} already fully processed.")
            chunk.status = "completed"
            chunk.save(update_fields=["status"])
            _check_and_trigger_finalize(chunk.report_id)  # Still check — may be the last chunk
            return {"chunk_id": chunk_id, "status": "finished"}

        from django.db.models import F
        for order_id in orders_to_process:
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(id=order_id)
                    # Process order logic...
                    chunk_revenue += Decimal(str(order.total_price))
                    success_count += 1
            except Exception as e:
                # SKIP ON FAILURE: Do not crash the chunk. Route to Dead Letter Table.
                logger.error(f"Failed to process order {order_id} in batch. Error: {e}")
                DeadLetterSales.objects.get_or_create(
                    report_id=chunk.report_id,
                    order_id=order_id,
                    defaults={"error_reason": str(e)}
                )

        # Mark chunk as fully completed and update chunk progress (Bookmark) once
        chunk.processed_count = chunk.processed_count + success_count
        chunk.total_revenue = chunk.total_revenue + chunk_revenue
        chunk.status = "completed"
        chunk.save(update_fields=["processed_count", "total_revenue", "status"])

        # Update master report stats safely once
        if success_count > 0:
            report.processed_orders = F('processed_orders') + success_count
            report.total_revenue = F('total_revenue') + chunk_revenue
            report.save(update_fields=["processed_orders", "total_revenue"])

        # Atomic finalization check — race-condition safe via CAS update
        _check_and_trigger_finalize(chunk.report_id)
        return {"chunk_id": chunk_id, "status": "finished"}

    except Exception as exc:
        try:
            # Retry with exponential backoff for transient failures (DB timeout, etc.)
            self.retry(exc=exc, countdown=2 ** self.request.retries, max_retries=3)
        except self.MaxRetriesExceededError:
            # Permanent failure after all retries.
            # Mark chunk "failed" so it no longer blocks _check_and_trigger_finalize.
            logger.error(
                f"Chunk {chunk_id} permanently failed after {self.max_retries} retries: {exc}"
            )
            SalesProcessingChunk.objects.filter(pk=chunk_id).update(status="failed")
            try:
                report_id = SalesProcessingChunk.objects.values_list(
                    "report_id", flat=True
                ).get(pk=chunk_id)
                _check_and_trigger_finalize(report_id)
            except Exception as inner:
                logger.error(
                    f"Could not trigger finalization after chunk {chunk_id} "
                    f"permanent failure: {inner}"
                )


@shared_task(bind=True)
def finalize_sales_batch(self, chunk_results, report_id: int):
    """
    Final callback executed when all chunks are completely finished.
    Generates the final PDF report.
    """
    report = DailySalesReport.objects.get(pk=report_id)

    # Idempotency guard: if already completed (e.g. called twice due to an unexpected
    # retry of finalize_sales_batch itself), skip without regenerating the PDF.
    if report.status == "completed":
        logger.info(f"Report {report_id} already finalized. Skipping duplicate call.")
        return {"report_id": report_id, "status": "already_completed"}

    # Check if any chunks failed critically
    failed_chunks = SalesProcessingChunk.objects.filter(report=report, status="failed").count()
    if failed_chunks > 0:
        logger.warning(f"Batch {report_id} finished but {failed_chunks} chunks failed completely.")
    
    # 1. GATHER ADVANCED ANALYTICS
    from django.db.models import Count, Sum, Avg
    from store.models import OrderItem, Product
    
    # All orders for this specific report date
    orders = Order.objects.filter(status="completed", created_at__date=report.date)
    
    unique_customers = orders.values('user').distinct().count()
    aov = orders.aggregate(avg_val=Avg('total_price'))['avg_val'] or 0
    
    # Top 5 Customers by Revenue
    top_customers = orders.values('user__email').annotate(
        total_spend=Sum('total_price'),
        order_count=Count('id')
    ).order_by('-total_spend')[:5]
    
    # Top 3 Products by Quantity
    top_products = OrderItem.objects.filter(order__in=orders).values('product__name').annotate(
        total_qty=Sum('quantity')
    ).order_by('-total_qty')[:3]

    # 2. GENERATE ENRICHED PDF REPORT
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from django.conf import settings
    import os
    
    timestamp = timezone.now().strftime('%H%M%S')
    pdf_filename = f"daily_sales_{report.date.strftime('%Y%m%d')}_{timestamp}.pdf"
    pdf_path = os.path.join(settings.BASE_DIR, pdf_filename)
    
    import time
    pdf_start = time.perf_counter()
    try:
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(100, 750, f"Daily Sales Performance Report")
        c.setFont("Helvetica", 12)
        c.drawString(100, 730, f"Report Date: {report.date}")
        c.drawString(100, 715, f"Generated At: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.drawString(100, 700, f"Operational Status: SUCCESS")

        # Basic Stats Table
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, 650, "1. Executive Summary")
        c.setFont("Helvetica", 11)
        c.drawString(120, 630, f"Total Orders: {report.total_orders}")
        c.drawString(120, 610, f"Processed Orders: {report.processed_orders}")
        c.drawString(120, 590, f"Total Revenue Generated: ${report.total_revenue:,.2f}")
        c.drawString(120, 570, f"Unique Active Customers: {unique_customers}")
        c.drawString(120, 550, f"Average Order Value (AOV): ${float(aov):,.2f}")

        # Top Customers Table
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, 500, "2. Top 5 High-Value Customers")
        y = 480
        c.setFont("Helvetica", 11)
        for i, cust in enumerate(top_customers, 1):
            c.drawString(120, y, f"{i}. {cust['user__email']} - ${float(cust['total_spend']):,.2f} ({cust['order_count']} orders)")
            y -= 20

        # Top Selling Products
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, y - 20, "3. Top 3 Highest-Selling Products")
        y -= 40
        c.setFont("Helvetica", 11)
        for i, prod in enumerate(top_products, 1):
            c.drawString(120, y, f"{i}. {prod['product__name']} - {prod['total_qty']} units sold")
            y -= 20

        # Operational Metrics
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, y - 20, "4. Operational Integrity")
        y -= 40
        c.setFont("Helvetica", 11)
        dead_letters = DeadLetterSales.objects.filter(report=report).count()
        c.drawString(120, y, f"Successful Processing Rate: {((report.processed_orders/report.total_orders)*100 if report.total_orders > 0 else 100):.1f}%")
        c.drawString(120, y - 20, f"Failed Records (Dead Letters): {dead_letters}")

        c.save()
        pdf_duration = time.perf_counter() - pdf_start
        report.pdf_report_path = pdf_path
        report.pdf_generation_time = round(pdf_duration, 4)
        logger.info(f"Enriched daily sales report completed in {pdf_duration:.4f}s! PDF saved to {pdf_path}")
    except Exception as e:
        pdf_duration = time.perf_counter() - pdf_start
        logger.error(f"Failed to generate enriched PDF report: {e}")
        report.pdf_report_path = f"Error generating PDF: {e}"
        report.pdf_generation_time = round(pdf_duration, 4)
    
    report.status = "completed"
    total_execution_duration = (timezone.now() - report.created_at).total_seconds()
    report.total_execution_time = round(total_execution_duration, 3)
    report.save(update_fields=["status", "pdf_report_path", "pdf_generation_time", "total_execution_time", "updated_at"])
    
    return {"report_id": report_id, "pdf_path": report.pdf_report_path}
