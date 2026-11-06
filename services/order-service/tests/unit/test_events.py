"""Unit tests: events.py pieces that need no real Redis."""
import json
import uuid
from unittest.mock import MagicMock

import events


def test_publish_builds_the_expected_stream_entry():
    r = MagicMock()
    r.xadd.return_value = "1-0"

    result = events.publish(r, "order_placed", "OrderPlaced", {"order_id": "o-1"})

    assert result == "1-0"
    args, kwargs = r.xadd.call_args
    assert args[0] == "order_placed"
    fields = args[1]
    assert fields["event_type"] == "OrderPlaced"
    assert json.loads(fields["payload"]) == {"order_id": "o-1"}
    uuid.UUID(fields["event_id"])            # raises if not a valid UUID
    assert fields["occurred_at"].isdigit()
    assert kwargs == {"maxlen": 10000, "approximate": True}


def test_publish_gives_every_event_a_unique_id():
    r = MagicMock()
    events.publish(r, "s", "T", {})
    events.publish(r, "s", "T", {})
    ids = [call.args[1]["event_id"] for call in r.xadd.call_args_list]
    assert ids[0] != ids[1]


def test_get_redis_uses_redis_url_env(monkeypatch):
    seen = {}

    def fake_from_url(url, **kwargs):
        seen["url"], seen["kwargs"] = url, kwargs
        return "client"

    monkeypatch.setenv("REDIS_URL", "rediss://example:6379")
    monkeypatch.setattr(events.redis.Redis, "from_url", fake_from_url)

    assert events.get_redis() == "client"
    assert seen["url"] == "rediss://example:6379"
    assert seen["kwargs"]["decode_responses"] is True


def test_get_redis_falls_back_to_localhost(monkeypatch):
    seen = {}
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(events.redis.Redis, "from_url",
                        lambda url, **kw: seen.setdefault("url", url))

    events.get_redis()
    assert seen["url"] == "redis://localhost:6379"


def test_log_prints_message(capsys):
    events.log("hello")
    assert capsys.readouterr().out == "hello\n"
