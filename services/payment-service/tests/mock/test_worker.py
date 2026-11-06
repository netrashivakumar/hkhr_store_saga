"""Mock tests: payment-service saga handler with a fake DB and fake publisher.

No Postgres, no Redis. These check the saga behaviour:
  StockReserved -> PaymentConfirmed | PaymentFailed (amount above PAYMENT_LIMIT)
plus idempotency: a duplicate delivery keeps the FIRST decision stored in the DB.
"""
import pytest

CONFIRMED_ROW = {"status": "CONFIRMED", "reason": None}


def failed_row(reason="amount 1800.00 exceeds limit 1000.00"):
    return {"status": "FAILED", "reason": reason}


def executed(calls, prefix):
    return [c for c in calls if c[0] == "execute" and c[1].startswith(prefix)]


def published(calls):
    return [c for c in calls if c[0] == "publish"]


def stock_reserved(amount, order_id="o-1"):
    return {"order_id": order_id, "item": "phone", "quantity": 1, "amount": amount}


# ---------- StockReserved ----------

def test_amount_within_limit_is_confirmed(run_worker):
    worker, calls = run_worker([CONFIRMED_ROW])

    worker.on_stock_reserved(stock_reserved(500))

    assert executed(calls, "INSERT INTO payments")[0][2] == ("o-1", 500.0, "CONFIRMED", None)
    assert published(calls) == [("publish", "payment_confirmed", "PaymentConfirmed", {
        "order_id": "o-1", "amount": 500.0})]


def test_amount_exactly_at_limit_is_confirmed(run_worker):
    worker, calls = run_worker([CONFIRMED_ROW])

    worker.on_stock_reserved(stock_reserved(worker.PAYMENT_LIMIT))

    assert executed(calls, "INSERT INTO payments")[0][2][2] == "CONFIRMED"
    assert published(calls)[0][2] == "PaymentConfirmed"


def test_amount_above_limit_is_declined(run_worker):
    reason = "amount 1800.00 exceeds limit 1000.00"
    worker, calls = run_worker([failed_row(reason)])

    worker.on_stock_reserved(stock_reserved(1800))

    assert executed(calls, "INSERT INTO payments")[0][2] == ("o-1", 1800.0, "FAILED", reason)
    assert published(calls) == [("publish", "payment_failed", "PaymentFailed", {
        "order_id": "o-1", "amount": 1800.0, "reason": reason})]


def test_limit_can_be_changed(run_worker, monkeypatch):
    worker, calls = run_worker([failed_row("amount 150.00 exceeds limit 100.00")])
    monkeypatch.setattr(worker, "PAYMENT_LIMIT", 100.0)

    worker.on_stock_reserved(stock_reserved(150))

    assert executed(calls, "INSERT INTO payments")[0][2] == (
        "o-1", 150.0, "FAILED", "amount 150.00 exceeds limit 100.00")
    assert published(calls)[0][2] == "PaymentFailed"


def test_amount_given_as_a_string_is_converted_to_a_number(run_worker):
    worker, calls = run_worker([CONFIRMED_ROW])

    worker.on_stock_reserved(stock_reserved("900.50"))

    assert executed(calls, "INSERT INTO payments")[0][2][1] == 900.5
    assert published(calls)[0][3]["amount"] == 900.5


# ---------- idempotency (duplicate deliveries) ----------

def test_insert_ignores_duplicates(run_worker):
    worker, calls = run_worker([CONFIRMED_ROW])

    worker.on_stock_reserved(stock_reserved(500))

    assert "ON CONFLICT (order_id) DO NOTHING" in executed(calls, "INSERT INTO payments")[0][1]


def test_duplicate_delivery_keeps_the_first_decline(run_worker):
    # DB already holds FAILED for this order, even though this delivery's amount is small
    worker, calls = run_worker([failed_row("first decision")])

    worker.on_stock_reserved(stock_reserved(10))

    assert published(calls) == [("publish", "payment_failed", "PaymentFailed", {
        "order_id": "o-1", "amount": 10.0, "reason": "first decision"})]


def test_duplicate_delivery_keeps_the_first_confirmation(run_worker):
    # DB already holds CONFIRMED, even though this delivery's amount is above the limit
    worker, calls = run_worker([CONFIRMED_ROW])

    worker.on_stock_reserved(stock_reserved(5000))

    assert [p[2] for p in published(calls)] == ["PaymentConfirmed"]


# ---------- ordering and failures ----------

def test_event_is_published_only_after_the_db_commit(run_worker):
    worker, calls = run_worker([CONFIRMED_ROW])

    worker.on_stock_reserved(stock_reserved(500))

    kinds = [c[0] for c in calls]
    assert kinds.index("commit") < kinds.index("publish")


def test_db_failure_publishes_nothing_and_propagates(run_worker, monkeypatch):
    worker, calls = run_worker([])

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(worker.db, "get_conn", boom)

    with pytest.raises(RuntimeError):     # so events._process can retry the message
        worker.on_stock_reserved(stock_reserved(500))
    assert published(calls) == []


def test_malformed_event_raises_so_it_can_be_retried_or_dead_lettered(run_worker):
    worker, calls = run_worker([])

    with pytest.raises(KeyError):
        worker.on_stock_reserved({"item": "phone"})     # no order_id / amount
    assert published(calls) == []
