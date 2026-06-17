import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")

import django
django.setup()

from store.services.sales.batch_processing import trigger_daily_sales_batch
from store.models.sales_report import DailySalesReport

def run():
    print("Triggering the Daily Sales Batch Job manually...")
    
    # We will clear out today's report if it exists so we can re-test it
    from django.utils import timezone
    from datetime import timedelta
    # We will target TODAY's date so we can see the results of your stress tests!
    target_date_str = timezone.now().date().strftime('2026-05-17')
    DailySalesReport.objects.filter(date=target_date_str).delete()
    
    # Trigger the task synchronously using the latest code
    start_time = time.time()
    report_id = trigger_daily_sales_batch(custom_date=target_date_str)
    print(f"Task dispatched! Master Report ID: {report_id}. Waiting for processing to complete...")
    
    while True:
        report = DailySalesReport.objects.get(pk=report_id)
        if report.status == "completed":
            break
        elif report.status == "failed":
            print("Batch report execution failed!")
            break
        time.sleep(0.5)
        
    elapsed = time.time() - start_time
    print(f"Script elapsed duration: {elapsed:.3f} seconds!")
    print(f"Total Batch Execution Time (Stored in DB): {report.total_execution_time:.3f} seconds!")
    print(f"Time needed to generate the PDF (Stored in DB): {report.pdf_generation_time:.4f} seconds!")

if __name__ == "__main__":
    run()
