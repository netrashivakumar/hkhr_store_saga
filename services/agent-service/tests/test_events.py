import json
from unittest.mock import Mock

import redis

from tools.events import get_order_events


def entry(event_type, order_id, occurred_at):
    return ("1-0", {
        "event_type": event_type,
        "occurred_at": occurred_at,
        "payload": json.dumps({"order_id": order_id}),
    })


def fake_redis(streams):
    r = Mock()
    r.xrevrange.side_effect = lambda name, count: streams.get(name, [])
    return r


def test_returns_events_in_time_order():
    r = fake_redis({
        "payment_failed": [entry("PaymentFailed", "123", "2000")],
        "order_placed": [entry("OrderPlaced", "123", "1000")],
    })
    result = get_order_events("123", r=r)
    types = [e["event_type"] for e in result["events"]]
    assert types == ["OrderPlaced", "PaymentFailed"]


def test_ignores_other_orders():
    r = fake_redis({"order_placed": [entry("OrderPlaced", "999", "1000")]})
    assert get_order_events("123", r=r)["events"] == []


def test_redis_error():
    r = Mock()
    r.xrevrange.side_effect = redis.ConnectionError("down")
    assert "could not read events" in get_order_events("123", r=r)["error"]


def test_missing_redis_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert "could not read events" in get_order_events("123")["error"]