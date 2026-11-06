"""Mock tests: inventory-service saga handlers with a fake DB and fake publisher.

No Postgres, no Redis. These check the saga behaviour:
  OrderPlaced   -> StockReserved | StockRejected
  PaymentFailed -> stock released (compensation)
plus idempotency (duplicate deliveries).
"""
from decimal import Decimal

import pytest

ORDER = {"order_id": "o-1", "item": "laptop", "quantity": 2}


def executed(calls, prefix):
    return [c for c in calls if c[0] == "execute" and c[1].startswith(prefix)]


def published(calls):
    return [c for c in calls if c[0] == "publish"]


# ---------- OrderPlaced ----------

def test_reserves_stock_and_publishes_stock_reserved(run_worker):
    worker, calls = run_worker([None, {"quantity": 5, "price": Decimal("900.00")}])

    worker.on_order_placed(ORDER)

    assert executed(calls, "UPDATE stock SET quantity = quantity - %s")[0][2] == (2, "laptop")
    assert executed(calls, "INSERT INTO reservations")[0][2] == (
        "o-1", "laptop", 2, Decimal("1800.00"))
    assert published(calls) == [("publish", "stock_reserved", "StockReserved", {
        "order_id": "o-1", "item": "laptop", "quantity": 2, "amount": 1800.0})]


def test_can_reserve_exactly_the_remaining_stock(run_worker):
    worker, calls = run_worker([None, {"quantity": 2, "price": Decimal("900.00")}])

    worker.on_order_placed(ORDER)

    assert published(calls)[0][2] == "StockReserved"


def test_rejects_when_stock_is_insufficient(run_worker):
    worker, calls = run_worker([None, {"quantity": 5, "price": Decimal("900.00")}])

    worker.on_order_placed({**ORDER, "quantity": 6})

    assert published(calls) == [("publish", "stock_rejected", "StockRejected", {
        "order_id": "o-1", "reason": "insufficient stock (5 left)"})]
    assert executed(calls, "UPDATE stock") == []
    assert executed(calls, "INSERT INTO reservations") == []


def test_rejects_unknown_item(run_worker):
    worker, calls = run_worker([None, None])

    worker.on_order_placed({**ORDER, "item": "unicorn"})

    assert published(calls) == [("publish", "stock_rejected", "StockRejected", {
        "order_id": "o-1", "reason": "unknown item"})]


def test_duplicate_delivery_republishes_without_reserving_twice(run_worker):
    existing = {"item": "laptop", "quantity": 2,
                "amount": Decimal("1800.00"), "status": "RESERVED"}
    worker, calls = run_worker([existing])

    worker.on_order_placed(ORDER)

    assert executed(calls, "UPDATE stock") == []
    assert executed(calls, "INSERT INTO reservations") == []
    assert executed(calls, "SELECT quantity, price FROM stock") == []
    assert published(calls) == [("publish", "stock_reserved", "StockReserved", {
        "order_id": "o-1", "item": "laptop", "quantity": 2, "amount": 1800.0})]


def test_duplicate_of_an_already_released_order_does_nothing(run_worker):
    existing = {"item": "laptop", "quantity": 2,
                "amount": Decimal("1800.00"), "status": "RELEASED"}
    worker, calls = run_worker([existing])

    worker.on_order_placed(ORDER)

    assert published(calls) == []
    assert executed(calls, "UPDATE stock") == []


def test_event_is_published_only_after_the_db_commit(run_worker):
    worker, calls = run_worker([None, {"quantity": 5, "price": Decimal("900.00")}])

    worker.on_order_placed(ORDER)

    kinds = [c[0] for c in calls]
    assert kinds.index("commit") < kinds.index("publish")


def test_db_failure_publishes_nothing_and_propagates(run_worker, monkeypatch):
    worker, calls = run_worker([])

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(worker.db, "get_conn", boom)

    with pytest.raises(RuntimeError):     # so events._process can retry the message
        worker.on_order_placed(ORDER)
    assert published(calls) == []


# ---------- PaymentFailed (compensation) ----------

def test_payment_failed_releases_reserved_stock(run_worker):
    worker, calls = run_worker([{"item": "laptop", "quantity": 2}])

    worker.on_payment_failed({"order_id": "o-1"})

    assert executed(calls, "UPDATE reservations SET status='RELEASED'")[0][2] == ("o-1",)
    assert executed(calls, "UPDATE stock SET quantity = quantity + %s")[0][2] == (2, "laptop")
    assert any("released 2 x laptop for o-1" in c[1] for c in calls if c[0] == "log")


def test_payment_failed_twice_does_not_release_stock_twice(run_worker):
    # second delivery: the UPDATE ... WHERE status='RESERVED' matches no row
    worker, calls = run_worker([])

    worker.on_payment_failed({"order_id": "o-1"})

    assert executed(calls, "UPDATE stock") == []
    assert published(calls) == []
