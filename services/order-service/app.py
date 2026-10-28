"""order-service: owns the orders database and the order lifecycle.

Publishes:  OrderPlaced, OrderCompleted, OrderFailed
Consumes:   StockReserved, StockRejected, PaymentConfirmed, PaymentFailed
"""
import os
import threading
import urllib.request
import uuid

import psycopg2
import redis
from flask import Flask, jsonify, request
from flask_cors import CORS

import db
import events

app = Flask(__name__)
CORS(app, origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","))
r = events.get_redis()

# Free Render services sleep when idle. After an order is accepted we ping
# these URLs (comma-separated) so the workers wake up and drain their streams.
WAKE_URLS = [u.strip() for u in os.environ.get("WAKE_URLS", "").split(",")
             if u.strip()]
OPEN_STATES = ["PENDING", "STOCK_RESERVED"]


def init_db():
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id   TEXT PRIMARY KEY,
                item       TEXT NOT NULL,
                quantity   INT NOT NULL,
                amount     NUMERIC(10,2),
                status     TEXT NOT NULL,
                reason     TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")


# ---------------------------- event handlers ----------------------------

def on_stock_reserved(p):
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE orders SET status='STOCK_RESERVED', amount=%s, "
            "updated_at=now() WHERE order_id=%s AND status='PENDING'",
            (p["amount"], p["order_id"]))


def on_payment_confirmed(p):
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE orders SET status='COMPLETED', amount=%s, updated_at=now() "
            "WHERE order_id=%s AND status = ANY(%s)",
            (p["amount"], p["order_id"], OPEN_STATES))
        cur.execute(
            "SELECT item, quantity, amount, status FROM orders "
            "WHERE order_id=%s", (p["order_id"],))
        row = cur.fetchone()
    # Publish after commit. If publishing fails, the retry re-publishes
    # (at-least-once), so consumers must be idempotent.
    if row and row["status"] == "COMPLETED":
        events.publish(r, "order_completed", "OrderCompleted", {
            "order_id": p["order_id"],
            "item": row["item"],
            "quantity": row["quantity"],
            "amount": float(row["amount"]),
        })


def _fail_order(order_id, reason):
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE orders SET status='FAILED', reason=%s, updated_at=now() "
            "WHERE order_id=%s AND status = ANY(%s)",
            (reason, order_id, OPEN_STATES))
        cur.execute("SELECT status, reason FROM orders WHERE order_id=%s",
                    (order_id,))
        row = cur.fetchone()
    if row and row["status"] == "FAILED":
        events.publish(r, "order_failed", "OrderFailed",
                       {"order_id": order_id, "reason": row["reason"]})


def on_stock_rejected(p):
    _fail_order(p["order_id"], "Stock: " + p["reason"])


def on_payment_failed(p):
    _fail_order(p["order_id"], "Payment: " + p["reason"])


# ------------------------------ HTTP API --------------------------------

def _serialize(row):
    return {
        "order_id": row["order_id"],
        "item": row["item"],
        "quantity": row["quantity"],
        "amount": float(row["amount"]) if row["amount"] is not None else None,
        "status": row["status"],
        "reason": row["reason"],
        "created_at": row["created_at"].isoformat(),
    }


def _ping(url):
    try:
        urllib.request.urlopen(url, timeout=90).read()
    except Exception:  # noqa: BLE001
        pass


def wake_services():
    for url in WAKE_URLS:
        threading.Thread(target=_ping, args=(url,), daemon=True).start()


@app.route("/api/order", methods=["POST"])
def place_order():
    data = request.get_json(silent=True) or {}
    item = str(data.get("item", "")).strip().lower()
    try:
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "quantity must be a number"}), 400
    if not item:
        return jsonify({"error": "item is required"}), 400
    if not 1 <= quantity <= 100:
        return jsonify({"error": "quantity must be between 1 and 100"}), 400

    order_id = str(uuid.uuid4())
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (order_id, item, quantity, status) "
                "VALUES (%s, %s, %s, 'PENDING')", (order_id, item, quantity))
    except psycopg2.Error as exc:
        events.log(f"[order-service] database error: {exc}")
        return jsonify({"error": "database unavailable"}), 503

    try:
        events.publish(r, "order_placed", "OrderPlaced", {
            "order_id": order_id, "item": item, "quantity": quantity})
    except redis.RedisError as exc:
        events.log(f"[order-service] publish failed: {exc}")
        _fail_order_quietly(order_id)
        return jsonify({"error": "event broker unavailable"}), 503

    wake_services()
    return jsonify({"status": "accepted", "order_id": order_id}), 202


def _fail_order_quietly(order_id):
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status='FAILED', reason=%s, updated_at=now() "
                "WHERE order_id=%s", ("event broker unavailable", order_id))
    except psycopg2.Error:
        pass


@app.route("/api/order/<order_id>")
def get_order(order_id):
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE order_id=%s", (order_id,))
            row = cur.fetchone()
    except psycopg2.Error:
        return jsonify({"error": "database unavailable"}), 503
    if row is None:
        return jsonify({"error": "order not found"}), 404
    return jsonify(_serialize(row))


@app.route("/health")
def health():
    return "ok", 200


# ------------------------ background event consumer ----------------------

def start_background_consumer():
    """Runs at import time so it also starts under gunicorn.

    Safe with several gunicorn workers: consumer groups split the messages.
    """
    init_db()
    handlers = {
        "stock_reserved": on_stock_reserved,
        "stock_rejected": on_stock_rejected,
        "payment_confirmed": on_payment_confirmed,
        "payment_failed": on_payment_failed,
    }
    threading.Thread(target=events.consume,
                     args=(r, "order-service", handlers),
                     daemon=True).start()


start_background_consumer()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
