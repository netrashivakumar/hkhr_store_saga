"""Mock tests: order-service EVENT handlers with a fake DB and fake publisher.

  StockReserved    -> order moves PENDING -> STOCK_RESERVED
  PaymentConfirmed -> order COMPLETED + publish OrderCompleted
  StockRejected / PaymentFailed -> order FAILED + publish OrderFailed
Status guards (WHERE status ...) make the handlers safe against duplicates and
late or out-of-order events.
"""
from decimal import Decimal

import pytest


def executed(calls, prefix):
    return [c for c in calls if c[0] == "execute" and c[1].startswith(prefix)]


def published(calls):
    return [c for c in calls if c[0] == "publish"]


COMPLETED_ROW = {"item": "phone", "quantity": 1,
                 "amount": Decimal("500.00"), "status": "COMPLETED"}


# ---------- StockReserved ----------

def test_stock_reserved_moves_a_pending_order_forward(run_app):
    app, calls = run_app()

    app.on_stock_reserved({"order_id": "o-1", "amount": 500.0})

    update = executed(calls, "UPDATE orders SET status='STOCK_RESERVED'")[0]
    assert update[2] == (500.0, "o-1")
    assert "status='PENDING'" in update[1]      # only a PENDING order may move
    assert published(calls) == []


# ---------- PaymentConfirmed ----------

def test_payment_confirmed_completes_order_and_publishes_order_completed(run_app):
    # Also what a duplicate delivery looks like: the UPDATE matches nothing,
    # the SELECT shows COMPLETED, and the event is re-published (at-least-once).
    app, calls = run_app([COMPLETED_ROW])

    app.on_payment_confirmed({"order_id": "o-1", "amount": 500.0})

    update = executed(calls, "UPDATE orders SET status='COMPLETED'")[0]
    assert update[2] == (500.0, "o-1", app.OPEN_STATES)
    assert published(calls) == [("publish", "order_completed", "OrderCompleted", {
        "order_id": "o-1", "item": "phone", "quantity": 1, "amount": 500.0})]


def test_payment_confirmed_for_an_already_failed_order_publishes_nothing(run_app):
    app, calls = run_app([{**COMPLETED_ROW, "status": "FAILED"}])

    app.on_payment_confirmed({"order_id": "o-1", "amount": 500.0})

    assert published(calls) == []


def test_payment_confirmed_for_an_unknown_order_publishes_nothing(run_app):
    app, calls = run_app([])        # SELECT finds no row

    app.on_payment_confirmed({"order_id": "nope", "amount": 500.0})

    assert published(calls) == []


def test_order_completed_is_published_only_after_the_db_commit(run_app):
    app, calls = run_app([COMPLETED_ROW])

    app.on_payment_confirmed({"order_id": "o-1", "amount": 500.0})

    kinds = [c[0] for c in calls]
    assert kinds.index("commit") < kinds.index("publish")


# ---------- StockRejected / PaymentFailed -> OrderFailed ----------

def test_stock_rejected_fails_the_order_and_publishes_order_failed(run_app):
    reason = "Stock: insufficient stock (5 left)"
    app, calls = run_app([{"status": "FAILED", "reason": reason}])

    app.on_stock_rejected({"order_id": "o-1", "reason": "insufficient stock (5 left)"})

    update = executed(calls, "UPDATE orders SET status='FAILED'")[0]
    assert update[2] == (reason, "o-1", app.OPEN_STATES)
    assert published(calls) == [("publish", "order_failed", "OrderFailed", {
        "order_id": "o-1", "reason": reason})]


def test_payment_failed_fails_the_order_with_a_payment_reason(run_app):
    reason = "Payment: amount 1800.00 exceeds limit 1000.00"
    app, calls = run_app([{"status": "FAILED", "reason": reason}])

    app.on_payment_failed({"order_id": "o-1",
                           "reason": "amount 1800.00 exceeds limit 1000.00"})

    assert executed(calls, "UPDATE orders SET status='FAILED'")[0][2][0] == reason
    assert published(calls)[0][2] == "OrderFailed"


def test_failure_event_for_an_already_completed_order_publishes_nothing(run_app):
    # a late failure must not turn a COMPLETED order into FAILED
    app, calls = run_app([{"status": "COMPLETED", "reason": None}])

    app.on_payment_failed({"order_id": "o-1", "reason": "late"})

    assert published(calls) == []


def test_failure_event_for_an_unknown_order_publishes_nothing(run_app):
    app, calls = run_app([])

    app.on_stock_rejected({"order_id": "nope", "reason": "x"})

    assert published(calls) == []


def test_order_failed_is_published_only_after_the_db_commit(run_app):
    app, calls = run_app([{"status": "FAILED", "reason": "Stock: x"}])

    app.on_stock_rejected({"order_id": "o-1", "reason": "x"})

    kinds = [c[0] for c in calls]
    assert kinds.index("commit") < kinds.index("publish")


# ---------- failures propagate so events._process can retry ----------

def test_db_failure_propagates_and_publishes_nothing(run_app, monkeypatch):
    app, calls = run_app([])

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(app.db, "get_conn", boom)

    with pytest.raises(RuntimeError):
        app.on_payment_confirmed({"order_id": "o-1", "amount": 500.0})
    assert published(calls) == []


def test_malformed_event_raises(run_app):
    app, calls = run_app([])

    with pytest.raises(KeyError):
        app.on_stock_rejected({"order_id": "o-1"})      # no "reason"
    assert published(calls) == []
