"""Mock tests: order-service HTTP API through Flask's test client.

DB and Redis are faked, so no real database or broker is contacted.
"""
import uuid
from datetime import datetime
from decimal import Decimal

import psycopg2
import pytest
import redis


def executed(calls, prefix):
    return [c for c in calls if c[0] == "execute" and c[1].startswith(prefix)]


def published(calls):
    return [c for c in calls if c[0] == "publish"]


# ---------- POST /api/order: success ----------

def test_valid_order_is_accepted_saved_and_published(run_app, client):
    app, calls = run_app()

    resp = client.post("/api/order", json={"item": "phone", "quantity": 2})

    assert resp.status_code == 202
    body = resp.get_json()
    assert body["status"] == "accepted"
    order_id = body["order_id"]
    uuid.UUID(order_id)                                   # valid UUID
    assert executed(calls, "INSERT INTO orders")[0][2] == (order_id, "phone", 2)
    assert published(calls) == [("publish", "order_placed", "OrderPlaced", {
        "order_id": order_id, "item": "phone", "quantity": 2})]
    assert ("wake",) in calls


def test_item_is_trimmed_and_lowercased(run_app, client):
    app, calls = run_app()

    client.post("/api/order", json={"item": "  Phone ", "quantity": 1})

    assert executed(calls, "INSERT INTO orders")[0][2][1] == "phone"


def test_quantity_defaults_to_one(run_app, client):
    app, calls = run_app()

    resp = client.post("/api/order", json={"item": "book"})

    assert resp.status_code == 202
    assert executed(calls, "INSERT INTO orders")[0][2][2] == 1


@pytest.mark.parametrize("quantity", [1, 100])
def test_quantity_limits_are_inclusive(run_app, client, quantity):
    app, calls = run_app()

    resp = client.post("/api/order", json={"item": "book", "quantity": quantity})

    assert resp.status_code == 202


def test_order_is_saved_before_the_event_is_published(run_app, client):
    app, calls = run_app()

    client.post("/api/order", json={"item": "phone", "quantity": 1})

    kinds = [c[0] for c in calls]
    assert kinds.index("commit") < kinds.index("publish")


# ---------- POST /api/order: validation ----------

@pytest.mark.parametrize("body, message", [
    ({}, "item is required"),
    ({"item": "   ", "quantity": 1}, "item is required"),
    ({"item": "phone", "quantity": "abc"}, "quantity must be a number"),
    ({"item": "phone", "quantity": None}, "quantity must be a number"),
    ({"item": "phone", "quantity": 0}, "quantity must be between 1 and 100"),
    ({"item": "phone", "quantity": -3}, "quantity must be between 1 and 100"),
    ({"item": "phone", "quantity": 101}, "quantity must be between 1 and 100"),
])
def test_invalid_orders_are_rejected_with_400(run_app, client, body, message):
    app, calls = run_app()

    resp = client.post("/api/order", json=body)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": message}
    assert executed(calls, "INSERT INTO orders") == []
    assert published(calls) == []


def test_non_json_body_is_rejected_with_400(run_app, client):
    app, calls = run_app()

    resp = client.post("/api/order", data="not json")

    assert resp.status_code == 400
    assert published(calls) == []


# ---------- POST /api/order: infrastructure failures ----------

def test_database_failure_returns_503_and_publishes_nothing(run_app, client, monkeypatch):
    app, calls = run_app()

    def down():
        raise psycopg2.OperationalError("db down")

    monkeypatch.setattr(app.db, "get_conn", down)

    resp = client.post("/api/order", json={"item": "phone", "quantity": 1})

    assert resp.status_code == 503
    assert resp.get_json() == {"error": "database unavailable"}
    assert published(calls) == []


def test_broker_failure_returns_503_and_marks_the_order_failed(run_app, client, monkeypatch):
    app, calls = run_app()

    def broker_down(r, stream, event_type, payload):
        raise redis.RedisError("broker down")

    monkeypatch.setattr(app.events, "publish", broker_down)

    resp = client.post("/api/order", json={"item": "phone", "quantity": 1})

    assert resp.status_code == 503
    assert resp.get_json() == {"error": "event broker unavailable"}
    order_id = executed(calls, "INSERT INTO orders")[0][2][0]
    update = executed(calls, "UPDATE orders SET status='FAILED'")[0]
    assert update[2] == ("event broker unavailable", order_id)
    assert ("wake",) not in calls                  # workers are not woken for a lost order


# ---------- GET /api/order/<id> ----------

def test_get_order_returns_the_order(run_app, client):
    row = {"order_id": "o-1", "item": "phone", "quantity": 1,
           "amount": Decimal("500.00"), "status": "COMPLETED", "reason": None,
           "created_at": datetime(2026, 11, 6, 12, 0, 0)}
    app, calls = run_app([row])

    resp = client.get("/api/order/o-1")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "order_id": "o-1", "item": "phone", "quantity": 1, "amount": 500.0,
        "status": "COMPLETED", "reason": None,
        "created_at": "2026-11-06T12:00:00"}
    assert executed(calls, "SELECT * FROM orders")[0][2] == ("o-1",)


def test_get_unknown_order_returns_404(run_app, client):
    app, calls = run_app([])

    resp = client.get("/api/order/nope")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "order not found"}


def test_get_order_database_failure_returns_503(run_app, client, monkeypatch):
    app, calls = run_app()

    def down():
        raise psycopg2.OperationalError("db down")

    monkeypatch.setattr(app.db, "get_conn", down)

    resp = client.get("/api/order/o-1")

    assert resp.status_code == 503
    assert resp.get_json() == {"error": "database unavailable"}


# ---------- /health ----------

def test_health_returns_ok(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "ok"
