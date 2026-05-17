# Run The Project

## Requirements

- Python 3.9+
- XAMPP
- MySQL/MariaDB running from XAMPP
- Database name: `ecommerce_db`

## Open Project Folder

```powershell
cd D:\Django\ecommerce_backend
```

## Create Database

Open phpMyAdmin and run if the database does not already exist:

```sql
CREATE DATABASE ecommerce_db;
```

Do not drop the database if it already contains project data. The Django models map to the existing FastAPI tables.

## Create Virtual Environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\activate
```

## Install Packages

```powershell
pip install -r requirements.txt
```

## Validate Django

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

The ecommerce models are unmanaged so Django will not create or delete the existing ecommerce tables.

## Run App

Make sure MySQL is running in XAMPP, then run:

```powershell
python manage.py runserver 127.0.0.1:8000
```

App URL:

```text
http://127.0.0.1:8000
```

## Nginx Commands

Use these from PowerShell:

```powershell
cd C:\Nginx\nginx-1.26.3
```

Start nginx:

```powershell
.\nginx.exe
```

Reload nginx config:

```powershell
.\nginx.exe -s reload
```

Stop nginx gracefully:

```powershell
.\nginx.exe -s stop
```

Show nginx status:

```powershell
Get-Process nginx
```

Force stop nginx if needed:

```powershell
Stop-Process -Name nginx -Force
```

## Celery Commands

Celery uses Redis from:

```python
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
```

Make sure Redis is running, then run these from the project folder:

```powershell
cd D:\Django\ecommerce_backend
```

Start Celery worker:

```powershell
celery -A ecommerce_backend worker --loglevel=info
```

Start Celery worker on Windows using solo pool:

```powershell
celery -A ecommerce_backend worker --loglevel=info --pool=solo
```

Show registered Celery tasks:

```powershell
celery -A ecommerce_backend inspect registered
```

Show active Celery tasks:

```powershell
celery -A ecommerce_backend inspect active
```

Stop Celery worker:

```powershell
Stop-Process -Name celery -Force
```

If Celery is running under Python directly:

```powershell
Get-Process python
Stop-Process -Id <PID> -Force
```

## API Endpoints

Scalar API docs:

```text
http://127.0.0.1:8000/docs
```

OpenAPI schema:

```text
http://127.0.0.1:8000/openapi.json
```

```text
GET    /
GET    /users?skip=0&limit=100
GET    /users/{user_id}
GET    /products?skip=0&limit=100
GET    /products/{product_id}
GET    /cart/{user_id}
POST   /cart/items
PUT    /cart/items/{cart_item_id}
DELETE /cart/items/{cart_item_id}
GET    /orders?user_id={user_id}&skip=0&limit=100
GET    /orders/user/{user_id}
GET    /orders/{order_id}
POST   /orders/checkout
```

Checkout requests still go through a server-side queue, then return the created order when processing succeeds. The checkout code uses database row locks plus a conditional stock update, so concurrent requests cannot sell more stock than is available.

## Run Seed Scripts

The original seed scripts still use the old SQLAlchemy setup. They are left in place for reference and should be migrated separately before using them with Django.


UPDATE products
SET stock_quantity = 20000
WHERE id = 1;
