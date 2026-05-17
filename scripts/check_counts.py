import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")
django.setup()

from django.utils import timezone
from store.models import Order

today = timezone.now().date()
total = Order.objects.filter(created_at__date=today).count()
completed = Order.objects.filter(status="completed", created_at__date=today).count()
pending = Order.objects.filter(status="pending", created_at__date=today).count()
failed = Order.objects.filter(status="failed", created_at__date=today).count()

print(f"--- STATUS REPORT FOR TODAY ({today}) ---")
print(f"Total Orders:     {total}")
print(f"Completed:        {completed}")
print(f"Pending:          {pending}")
print(f"Failed:           {failed}")
print(f"Sum (C+P+F):      {completed + pending + failed}")
