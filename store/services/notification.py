from time import sleep
from typing import Any

from celery import shared_task


@shared_task(name="store.send_notification")
def send_notification(*args: Any, **kwargs: Any) -> dict:
    sleep(2)
    return {
        "status": "sent",
        "args": args,
        "kwargs": kwargs,
    }
