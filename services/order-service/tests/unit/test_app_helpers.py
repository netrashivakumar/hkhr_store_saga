"""Unit tests: small helper functions in app.py (no DB, no Redis)."""
from datetime import datetime
from decimal import Decimal


def test_serialize_converts_types_for_json(app_module):
    row = {"order_id": "o-1", "item": "phone", "quantity": 2,
           "amount": Decimal("12.50"), "status": "COMPLETED", "reason": None,
           "created_at": datetime(2026, 11, 6, 12, 0, 0)}

    assert app_module._serialize(row) == {
        "order_id": "o-1", "item": "phone", "quantity": 2, "amount": 12.5,
        "status": "COMPLETED", "reason": None,
        "created_at": "2026-11-06T12:00:00"}


def test_serialize_keeps_missing_amount_as_none(app_module):
    row = {"order_id": "o-1", "item": "phone", "quantity": 1, "amount": None,
           "status": "PENDING", "reason": None,
           "created_at": datetime(2026, 11, 6, 12, 0, 0)}

    assert app_module._serialize(row)["amount"] is None


def test_ping_swallows_errors(app_module, monkeypatch):
    def boom(url, timeout):
        raise OSError("worker asleep")

    monkeypatch.setattr(app_module.urllib.request, "urlopen", boom)

    app_module._ping("http://worker")      # must not raise


def test_ping_calls_the_url_with_a_long_timeout(app_module, monkeypatch):
    seen = {}

    class Response:
        def read(self):
            return b"ok"

    def fake_urlopen(url, timeout):
        seen["url"], seen["timeout"] = url, timeout
        return Response()

    monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)

    app_module._ping("http://worker")

    assert seen == {"url": "http://worker", "timeout": 90}


def test_wake_services_pings_every_url_in_its_own_daemon_thread(app_module, monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.spec = (target, args, daemon)

        def start(self):
            started.append(self.spec)

    monkeypatch.setattr(app_module.threading, "Thread", FakeThread)
    monkeypatch.setattr(app_module, "WAKE_URLS", ["http://a", "http://b"])

    app_module.wake_services()

    assert started == [(app_module._ping, ("http://a",), True),
                       (app_module._ping, ("http://b",), True)]


def test_wake_services_does_nothing_when_no_urls_configured(app_module, monkeypatch):
    started = []
    monkeypatch.setattr(app_module.threading, "Thread",
                        lambda **kw: started.append(kw))
    monkeypatch.setattr(app_module, "WAKE_URLS", [])

    app_module.wake_services()

    assert started == []
