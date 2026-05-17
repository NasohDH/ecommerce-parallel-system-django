import os
import sys
from decimal import Decimal
from pathlib import Path
from random import Random


sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ecommerce_backend.settings")

import django
from django.db import connection


BALANCE_COLUMN_SQL = (
    "ALTER TABLE users "
    "ADD COLUMN balance DECIMAL(10, 2) NOT NULL DEFAULT 0"
)
BATCH_SIZE = 5_000
MAX_BALANCE_CENTS = 50_000
RANDOM_SEED = 2026


def balance_column_exists() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM users LIKE %s", ["balance"])
        return cursor.fetchone() is not None


def ensure_balance_column() -> None:
    if balance_column_exists():
        print("users.balance column already exists.")
        return

    with connection.cursor() as cursor:
        cursor.execute(BALANCE_COLUMN_SQL)
    print("Added users.balance column.")


def seed_user_balances() -> int:
    from store.models import User

    random = Random(RANDOM_SEED)
    updated_count = 0
    user_ids = list(User.objects.order_by("id").values_list("id", flat=True))

    for batch_start in range(0, len(user_ids), BATCH_SIZE):
        batch_user_ids = user_ids[batch_start : batch_start + BATCH_SIZE]
        users = list(User.objects.filter(id__in=batch_user_ids))

        for user in users:
            cents = random.randint(0, MAX_BALANCE_CENTS)
            user.balance = Decimal(cents) / Decimal("100")

        User.objects.bulk_update(users, ["balance"], batch_size=BATCH_SIZE)
        updated_count += len(users)

        processed = min(batch_start + BATCH_SIZE, len(user_ids))
        print(f"Seeded balances for {processed}/{len(user_ids)} users")

    return updated_count


def main() -> None:
    django.setup()
    ensure_balance_column()
    updated_count = seed_user_balances()
    print(f"Seeded balances for {updated_count} users.")


if __name__ == "__main__":
    main()
