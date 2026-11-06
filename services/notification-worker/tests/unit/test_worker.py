"""Unit tests: notification-worker handlers (the 'notification' is a log line)."""
import pytest

import worker

COMPLETED = {"order_id": "o-1", "item": "phone", "quantity": 2, "amount": 1000.0}


def test_order_completed_sends_a_confirmation(logged):
    worker.on_order_completed(COMPLETED)

    assert logged == ["[notification] ✅ Confirmation sent: order o-1 "
                      "(2 x phone, total $1000.00)"]


@pytest.mark.parametrize("amount, shown", [
    (5, "$5.00"),              # whole number
    (19.999, "$20.00"),        # rounds to cents
    (1234.5, "$1234.50"),      # pads to two decimals
])
def test_order_completed_formats_the_total_to_two_decimals(logged, amount, shown):
    worker.on_order_completed({**COMPLETED, "amount": amount})

    assert f"total {shown})" in logged[0]


def test_order_failed_sends_a_failure_notice_with_the_reason(logged):
    worker.on_order_failed({"order_id": "o-1",
                            "reason": "Payment: amount 1800.00 exceeds limit 1000.00"})

    assert logged == ["[notification] ❌ Failure notice sent: order o-1 - "
                      "Payment: amount 1800.00 exceeds limit 1000.00"]


@pytest.mark.parametrize("missing", ["order_id", "item", "quantity", "amount"])
def test_incomplete_completed_event_raises_so_it_can_be_retried(logged, missing):
    event = {k: v for k, v in COMPLETED.items() if k != missing}

    with pytest.raises(KeyError):
        worker.on_order_completed(event)
    assert logged == []         # no half-written notification


@pytest.mark.parametrize("missing", ["order_id", "reason"])
def test_incomplete_failed_event_raises_so_it_can_be_retried(logged, missing):
    event = {"order_id": "o-1", "reason": "x"}
    del event[missing]

    with pytest.raises(KeyError):
        worker.on_order_failed(event)
    assert logged == []
