"""inventory-service: owns the stock database.

Consumes:   OrderPlaced, PaymentFailed
Publishes:  StockReserved, StockRejected
Compensation: on PaymentFailed it releases the reserved stock.
"""
import db
import events

r = events.get_redis()

# item, quantity, price (the product catalog lives in this service)
SEED_STOCK = [
    ("laptop", 5, 900),
    ("phone", 10, 500),
    ("headphones", 20, 50),
    ("book", 100, 15),
]


def init_db():
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock (
                item     TEXT PRIMARY KEY,
                quantity INT NOT NULL CHECK (quantity >= 0),
                price    NUMERIC(10,2) NOT NULL
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                order_id   TEXT PRIMARY KEY,
                item       TEXT NOT NULL,
                quantity   INT NOT NULL,
                amount     NUMERIC(10,2) NOT NULL,
                status     TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
        for item, quantity, price in SEED_STOCK:
            cur.execute(
                "INSERT INTO stock (item, quantity, price) VALUES (%s, %s, %s) "
                "ON CONFLICT (item) DO NOTHING", (item, quantity, price))


def on_order_placed(p):
    order_id, item, quantity = p["order_id"], p["item"], p["quantity"]
    rejected_reason = None
    reserved = None

    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT item, quantity, amount, status FROM reservations "
                    "WHERE order_id=%s", (order_id,))
        existing = cur.fetchone()
        if existing:
            if existing["status"] != "RESERVED":
                return  # already released by a failed payment
            reserved = existing  # duplicate delivery: just re-publish
        else:
            cur.execute("SELECT quantity, price FROM stock WHERE item=%s "
                        "FOR UPDATE", (item,))
            row = cur.fetchone()
            if row is None:
                rejected_reason = "unknown item"
            elif row["quantity"] < quantity:
                rejected_reason = f"insufficient stock ({row['quantity']} left)"
            else:
                amount = row["price"] * quantity
                cur.execute("UPDATE stock SET quantity = quantity - %s "
                            "WHERE item=%s", (quantity, item))
                cur.execute(
                    "INSERT INTO reservations "
                    "(order_id, item, quantity, amount, status) "
                    "VALUES (%s, %s, %s, %s, 'RESERVED')",
                    (order_id, item, quantity, amount))
                reserved = {"item": item, "quantity": quantity,
                            "amount": amount}

    # Publish after the transaction commits.
    if rejected_reason:
        events.log(f"[inventory] rejected {order_id}: {rejected_reason}")
        events.publish(r, "stock_rejected", "StockRejected",
                       {"order_id": order_id, "reason": rejected_reason})
    else:
        events.log(f"[inventory] reserved {reserved['quantity']} x "
                   f"{reserved['item']} for {order_id}")
        events.publish(r, "stock_reserved", "StockReserved", {
            "order_id": order_id,
            "item": reserved["item"],
            "quantity": reserved["quantity"],
            "amount": float(reserved["amount"]),
        })


def on_payment_failed(p):
    """Compensating action: give the reserved stock back."""
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE reservations SET status='RELEASED' "
            "WHERE order_id=%s AND status='RESERVED' RETURNING item, quantity",
            (p["order_id"],))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE stock SET quantity = quantity + %s "
                        "WHERE item=%s", (row["quantity"], row["item"]))
            events.log(f"[inventory] released {row['quantity']} x "
                       f"{row['item']} for {p['order_id']} (payment failed)")


def main():
    init_db()
    events.start_health_server(5002)
    events.consume(r, "inventory-service", {
        "order_placed": on_order_placed,
        "payment_failed": on_payment_failed,
    })


if __name__ == "__main__":
    main()
