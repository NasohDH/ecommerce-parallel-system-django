from pathlib import Path

import pymysql


pymysql.install_as_MySQLdb()


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-ecommerce-backend-local-development-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django_prometheus",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "store",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "store.middleware.profiler.SafeTimingMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "ecommerce_backend.resource_middleware.ResourceManagerMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",

    "django_prometheus.middleware.PrometheusAfterMiddleware",
]


ROOT_URLCONF = "ecommerce_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "ecommerce_backend.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "ecommerce_db",
        "USER": "root",
        "PASSWORD": "",
        "HOST": "localhost",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/2",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
APPEND_SLASH = False
SYSTEM_MAX_WORKERS = 20
SYSTEM_MAX_QUEUE_SIZE = 100
SYSTEM_TASK_TIMEOUT = 20
MONITORED_SERVER_URLS = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],    "UNAUTHENTICATED_USER": None,
}


CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_IMPORTS = ("store.tasks",)

CELERY_TIMEZONE = "Asia/Baghdad"

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "daily_sales_batch_job": {
        "task": "store.services.sales.batch_processing.trigger_daily_sales_batch",
        "schedule": crontab(hour=0, minute=0),
    },
}
