#  Beginner's Guide: Understanding the Parallel E-commerce System

Welcome! Since this is your first time working with Django and you're building a system designed for "Parallelism" (handling many things at once), this guide will explain the concepts from scratch with real-world analogies and code examples.

---

## 1. What is Django?
Think of Django as a **highly organized construction kit** for websites.
*   **The Request**: When a user clicks a button, a "Request" is sent to your server.
*   **The URL**: Django looks at `urls.py` to see where to send that request (like a GPS).
*   **The View**: A function (in `views/`) that decides what to do.
*   **The Model**: A Python class that represents a database table (in `models/`).

---

## 2. Why a "Parallel" System?
In a normal shop, if 10,000 people try to buy the **last iPhone** at the exact same millisecond, the server might crash, or worse, sell the same iPhone to all 10,000 people.

Our system uses **3 layers of protection** to handle this:

### Layer 1: The Admission Gate (Throttling)
**Analogy:** A security guard at a club door.
*   **File:** `resource_manager.py` & `resource_middleware.py`
*   **How it works:** We use a **Semaphore** (a counter). If `MAX_WORKERS` is 5, only 5 requests can be processed at once. The 6th person has to wait in a "Queue." If the queue is also full, they are told "Come back later" (HTTP 503 error).
*   **Code Example:**
    ```python
    # In resource_manager.py
    self._workers = BoundedSemaphore(5) # Only 5 people in the "room"
    ```

### Layer 2: The Checkout Queue (Job Serializer)
**Analogy:** A single line at a coffee shop register.
*   **File:** `checkout_queue.py`
*   **How it works:** Even if 5 requests are running, they all might try to update the database. For sensitive things like "Checkout," we put them in a strict **Python Queue**. One worker thread processes them one-by-one to ensure we never lose track of stock.
*   **Why?** This prevents "Race Conditions" where two processes try to change the same stock number at once.

### Layer 3: Database Row Locking
**Analogy:** Putting a "Reserved" sign on a table.
*   **File:** `store/services/order/order_checkout.py`
*   **How it works:** We use `select_for_update()`. When the code reads a product's stock, it "locks" that row in the database. No other part of the system can touch that specific product until the current transaction is finished.
*   **Code Example:**
    ```python
    # Locked so no one else can change stock while we check it
    product = Product.objects.select_for_update().get(id=1)
    ```

---

## 3. The Journey of a "Checkout" Request

Here is exactly what happens when a user clicks "Buy":

1.  **Arrival**: The request hits `resource_middleware.py`.
2.  **Permission**: The Middleware asks `resource_manager`: "Is there a free worker thread?"
    *   *If yes*: Proceed.
    *   *If no*: Wait in the global queue.
3.  **View**: The request reaches `OrderViewSet.checkout` in `store/views/orders.py`.
4.  **The Internal Queue**: The view calls `checkout_queue.checkout(user_id)`.
    *   The request is put into a "Job" list.
    *   The code **blocks** (waits) here until the background worker finishes the job.
5.  **The Processing**: The background worker (in `checkout_queue.py`) picks up the job and calls `checkout_cart`.
6.  **The Transaction**: Inside `order_checkout.py`:
    *   Open a `transaction.atomic()` (All or nothing).
    *   Lock the Cart and Products.
    *   Check if stock > quantity.
    *   Reduce stock and create the Order.
7.  **Asynchronous Finish**: Once the database is saved, it tells **Celery** to send a notification. The user doesn't have to wait for the email to be sent; it happens in the background.
8.  **Completion**: The `checkout_queue` releases the result, the view sends the JSON response, and the `resource_middleware` releases the worker slot for the next person.

---

## 4. Key Terms for You
*   **Middleware**: Code that runs *before* every request. Perfect for security and throttling.
*   **Atomic Transaction**: A group of database changes that either all succeed or all fail. Never half-finished!
*   **Celery**: A tool to run "Background Tasks" (like sending emails) so the user doesn't have to wait.
*   **Prometheus**: The system we use to create those "Live Metrics" charts you see on the dashboard.

---

## 5. Summary Table

| Goal | Tool Used | Location |
| :--- | :--- | :--- |
| **Limit Users** | Semaphores | `resource_manager.py` |
| **Protect Stock** | Row Locking | `order_checkout.py` |
| **Handle High Load** | Job Queue | `checkout_queue.py` |
| **Send Emails Fast** | Celery | `tasks.py` |
| **Watch the System** | Dashboard | `urls.py` |
