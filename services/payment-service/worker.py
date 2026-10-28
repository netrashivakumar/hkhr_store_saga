"""payment-service: owns the payments database.

Consumes:   StockReserved
Publishes:  PaymentConfirmed, PaymentFailed

Payments are simulated: any amount above PAYMENT_LIMIT is declined,
which lets you trigger the failure/compensation path on purpose.
"""
import os

import db
import events

r = events.get_redis()
PAYMENT_LIMIT = float(os.environ.get("PAYMENT_LIMIT", "1000"))


def init_db():
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                order_id   TEXT PRIMARY KEY,
                amount     NUMERIC(10,2) NOT NULL,
                status     TEXT NOT NULL,
                reason     TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")


def on_stock_reserved(p):
    order_id = p["order_id"]
    amount = float(p["amount"])
    if amount > PAYMENT_LIMIT:
        status = "FAILED"
        reason = f"amount {amount:.2f} exceeds limit {PAYMENT_LIMIT:.2f}"
    else:
        status, reason = "CONFIRMED", None

    with db.get_conn() as conn, conn.cursor() as cur:
        # Idempotent: a duplicate delivery keeps the first decision.
        cur.execute(
            "INSERT INTO payments (order_id, amount, status, reason) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (order_id) DO NOTHING",
            (order_id, amount, status, reason))
        cur.execute("SELECT status, reason FROM payments WHERE order_id=%s",
                    (order_id,))
        row = cur.fetchone()

    if row["status"] == "CONFIRMED":
        events.log(f"[payment] confirmed {amount:.2f} for {order_id}")
        events.publish(r, "payment_confirmed", "PaymentConfirmed",
                       {"order_id": order_id, "amount": amount})
    else:
        events.log(f"[payment] failed for {order_id}: {row['reason']}")
        events.publish(r, "payment_failed", "PaymentFailed", {
            "order_id": order_id, "amount": amount, "reason": row["reason"]})


def main():
    init_db()
    events.start_health_server(5004)
    events.consume(r, "payment-service", {"stock_reserved": on_stock_reserved})


if __name__ == "__main__":
    main()
