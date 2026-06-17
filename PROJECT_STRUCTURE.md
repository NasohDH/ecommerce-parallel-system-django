# ️ Detailed Project Structure: E-commerce Parallel System

This document provides an exhaustive breakdown of every directory and file in the project, explaining their purpose, contents, and how they contribute to the high-concurrency architecture.

---

##  Root Directory
*   **`manage.py`**: The entry point for all Django administrative commands. It sets up the environment and executes commands like `runserver`, `migrate`, and `shell`.
*   **`requirements.txt`**: Lists all Python dependencies (Django, DRF, PyMySQL, Redis, Celery, etc.) required to run the project.
*   **`PROJECT_STRUCTURE.md`**: (This file) A guide to the system's architecture.
*   **`README.md`**: Installation and setup instructions.

---

## ️ `ecommerce_backend/` (Project Core)
This directory contains the global configuration and the "System Architecture" layers.

*   **`settings.py`**: The "Brain" of the project. Contains database credentials, Redis/Celery configuration, and custom parallel system "knobs" like `SYSTEM_MAX_WORKERS`.
*   **`urls.py`**: The main routing table. Unlike standard Django projects, this file also contains:
    *   **Live Dashboard**: A built-in HTML dashboard (`system_dashboard_view`) that visualizes system health in real-time.
    *   **Distributed Metrics**: Logic to aggregate metrics from multiple server instances.
*   **`resource_manager.py`**: **[CRITICAL]** Implements the `ResourceManager`. It uses two `BoundedSemaphore` objects to act as an "Admission Gate," controlling exactly how many requests are processed or queued at once.
*   **`resource_middleware.py`**: A custom Django middleware that intercepts every request. It calls `resource_manager.acquire()` before allowing a request to hit the database, ensuring the system never exceeds its capacity.
*   **`metrics.py`**: Defines custom Prometheus gauges and counters to track system performance, queue lengths, and rejection rates.
*   **`openapi.py`**: Contains the full JSON specification for the API (Swagger/OpenAPI). It defines all endpoints, request bodies, and response types.
*   **`celery.py`**: Configures Celery to use Redis for background task processing.
*   **`asgi.py` / `wsgi.py`**: Standard interfaces for web servers (like Gunicorn or Daphne) to communicate with the project.

---

##  `store/` (Business Logic App)
This app contains the e-commerce domain logic. It is organized into sub-packages for clarity.

### ️ `store/models/` (Data Layer)
*   *Note: All models use `managed = False` to map to an existing external database.*
*   **`user.py`**: Maps to the `users` table.
*   **`product.py`**: Maps to the `products` table (includes stock management).
*   **`cart.py`**: Maps to `carts` and `cart_items` tables.
*   **`order.py`**: Maps to `orders` and `order_items` tables.

###  `store/serializers/` (Data Transformation)
*   Contains Django Rest Framework (DRF) serializers that convert database model instances into JSON format for the API.

###  `store/views/` (Controllers)
*   **`products.py` / `users.py` / `cart.py`**: Standard API views for CRUD operations.
*   **`orders.py`**: Contains the complex checkout logic which interacts with the queue system.
*   **`pagination.py`**: Utility for consistent `skip` and `limit` handling across all list endpoints.

###  `store/services/` (Business Logic Layer)
This is where the complex operations happen, separated from the views.
*   **`checkout_queue.py`**: **[CRITICAL]** Implements a thread-safe internal queue. When a user checks out, their request is enqueued here to be processed sequentially, preventing race conditions (like over-selling stock).
*   **`order/order_checkout.py`**: Contains the actual database transaction logic for creating an order and reducing stock.
*   **`payment.py` / `notification.py`**: Mock services for handling payments and sending user alerts.

###  `store/tasks.py`
*   Contains Celery tasks that run in the background (asynchronous), such as database cleanup or periodic reporting.

---

##  `scripts/`
*   Contains Python scripts used to populate the database with seed data (`seed.py`) or perform stress tests.

---

##  System Interaction Summary

1.  **Request Arrival**: `resource_middleware.py` catches the request.
2.  **Throttling**: `resource_manager.py` checks if there is room in the worker pool or queue.
3.  **Routing**: `urls.py` sends the request to the appropriate `views/`.
4.  **Serialization**: `serializers/` validates the incoming JSON data.
5.  **Logic Execution**: The `views/` call a `services/` function to perform the work.
    *   *Example: Checkout calls `checkout_queue.py` to handle the request safely.*
6.  **Database Access**: `models/` fetch or update data in MySQL.
7.  **Response**: The result is serialized back to JSON and returned to the user.
8.  **Monitoring**: Every step updates a metric in `metrics.py`, which shows up on your dashboard.
