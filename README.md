# 🛒 hkhr_store: Event-Driven Microservices with a Saga

Five small services, each with its **own responsibility and its own database**,
cooperating only through **events** on Upstash Redis Streams.

## The order saga (choreography)

```text
 Browser ──POST /api/order──> order-service ──(orders DB: PENDING)
                                   │ OrderPlaced
                                   ▼
                          inventory-service ──(inventory DB: reserve stock)
                           │ StockReserved            │ StockRejected ──────┐
                           ▼                          │                     │
                    payment-service ──(payments DB)   │                     │
                     │ PaymentConfirmed │ PaymentFailed                     │
                     │                  ├──> inventory-service releases     │
                     │                  │    the stock (compensation)       │
                     ▼                  ▼                                   ▼
                              order-service updates its row
                          OrderCompleted          OrderFailed
                                   └────────┬────────┘
                                            ▼
                                   notification-worker
```

| Event | Stream | Published by | Consumed by |
|---|---|---|---|
| OrderPlaced | `order_placed` | order-service | inventory-service |
| StockReserved | `stock_reserved` | inventory-service | payment-service, order-service |
| StockRejected | `stock_rejected` | inventory-service | order-service |
| PaymentConfirmed | `payment_confirmed` | payment-service | order-service |
| PaymentFailed | `payment_failed` | payment-service | order-service, inventory-service |
| OrderCompleted | `order_completed` | order-service | notification-worker |
| OrderFailed | `order_failed` | order-service | notification-worker |
| (poison messages) | `dead_letter` | any consumer | you, for inspection |

Order status in the orders DB moves `PENDING → STOCK_RESERVED → COMPLETED` or `FAILED`.

## Services and databases

| Service | Folder | Database | Start command |
|---|---|---|---|
| frontend | `services/frontend` | none | `gunicorn app:app` |
| order-service | `services/order-service` | `orders` table | `gunicorn app:app --workers 1 --threads 4` |
| inventory-service | `services/inventory-service` | `stock`, `reservations` | `python worker.py` |
| payment-service | `services/payment-service` | `payments` | `python worker.py` |
| notification-worker | `services/notification-worker` | none | `python worker.py` |

`events.py` and `db.py` are intentionally **copied** into each service: services
never import each other's code.

## Free stack

GitHub + Actions + Codespaces, **Upstash Redis** (events), **Neon Postgres** (databases),
**Render** free web services (hosting). Check each provider's current free limits.

## 1. Create the databases (Neon)

Create a Neon project and three databases: `orders_db`, `inventory_db`, `payments_db`
(if your plan doesn't allow three, one database works too: the table names don't collide).
Copy each connection string (`postgresql://...?sslmode=require`).

## 2. Run locally (Codespaces)

```bash
export REDIS_URL="rediss://default:PASSWORD@your-endpoint.upstash.io:6379"
export DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require"   # same URL for all, locally
./run_local.sh
```
Open port 5000 and place orders. Watch the terminal for `[inventory]`, `[payment]`, `[notification]` lines.

## 3. Deploy on Render

Create one **Web Service** per row (same repo, set **Root Directory**, build command `pip install -r requirements.txt`).
Create the three workers first so you have their URLs.

| Service | Root Directory | Env vars |
|---|---|---|
| inventory-service | `services/inventory-service` | `REDIS_URL`, `DATABASE_URL` (inventory db) |
| payment-service | `services/payment-service` | `REDIS_URL`, `DATABASE_URL` (payments db), optional `PAYMENT_LIMIT` (default 1000) |
| notification-worker | `services/notification-worker` | `REDIS_URL` |
| order-service | `services/order-service` | `REDIS_URL`, `DATABASE_URL` (orders db), `WAKE_URLS` (the three worker URLs, comma-separated), `ALLOWED_ORIGINS` (frontend URL) |
| frontend | `services/frontend` | `ORDER_API_URL` (order-service URL) |

**Why `WAKE_URLS`?** Free Render services sleep after ~15 minutes without HTTP traffic,
and a sleeping worker can't read its stream. When an order is accepted, order-service
pings the workers so they wake up and process the backlog. The first order after idle
time can therefore take about a minute.

## 4. Things to try

| Order | What happens |
|---|---|
| Phone × 1 | Stock reserved → payment confirmed → **COMPLETED** |
| Laptop × 6 | Only 5 in stock → `StockRejected` → **FAILED** |
| Laptop × 2 | $1800 exceeds the $1000 limit → `PaymentFailed` → stock **released** → **FAILED** |

Then check the tables in Neon and the streams in Upstash's Data Browser.

## Concepts this project demonstrates

- **Database per service**: no service reads another service's tables.
- **Saga (choreography)**: a business transaction spread across services with no central coordinator.
- **Compensating transaction**: `PaymentFailed` makes inventory release the stock.
- **Idempotent consumers**: duplicate deliveries don't double-reserve or double-charge
  (unique `order_id` keys, status checks).
- **At-least-once delivery**: consumer groups + ack + retry after 30s + dead-letter stream.
- **Known limitation, the dual-write problem**: a service commits to its DB and then publishes.
  A crash in between is repaired by re-publishing on redelivery here, but production systems
  use the **transactional outbox pattern**. A good next exercise.
