import os
import sys
from pathlib import Path

# Setup Django environment
sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")

import django
from django.db import connection

def column_exists(table_name, column_name) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE %s", [column_name])
        return cursor.fetchone() is not None

def ensure_columns() -> None:
    django.setup()
    
    # Tables to check and their required columns
    schema_updates = [
        ("orders", "created_at", "ALTER TABLE orders ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ("order_items", "created_at", "ALTER TABLE order_items ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]

    with connection.cursor() as cursor:
        for table, column, sql in schema_updates:
            if not column_exists(table, column):
                print(f"Adding {column} to {table}...")
                cursor.execute(sql)
                print(f"Added {column} to {table}.")
            else:
                print(f"Column {column} already exists in {table}.")

if __name__ == "__main__":
    ensure_columns()
