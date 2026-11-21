from unittest.mock import Mock, patch

import redis

from tools.actions import republish_order_placed

STUCK = {"order_id": "1", "item": "laptop", "quantity": 2, "status": "PENDING"}


@patch("tools.actions.get_order_status")
def test_republishes_a_stuck_order(mock_status, monkeypatch):
    monkeypatch.delenv("STREAM_PREFIX", raising=False)
    mock_status.return_value = STUCK
    r = Mock()
    r.xadd.return_value = "1-0"
    assert republish_order_placed("1", r=r) == {"republished": "1", "message_id": "1-0"}
    stream, fields = r.xadd.call_args.args[:2]
    assert stream == "order_placed"
    assert fields["event_type"] == "OrderPlaced"
    assert '"item": "laptop"' in fields["payload"]


@patch("tools.actions.get_order_status")
def test_refuses_a_completed_order(mock_status):
    mock_status.return_value = {**STUCK, "status": "COMPLETED"}
    r = Mock()
    assert "COMPLETED" in republish_order_placed("1", r=r)["error"]
    r.xadd.assert_not_called()


@patch("tools.actions.get_order_status")
def test_passes_on_a_status_error(mock_status):
    mock_status.return_value = {"error": "order 9 not found"}
    r = Mock()
    assert republish_order_placed("9", r=r) == {"error": "order 9 not found"}
    r.xadd.assert_not_called()


@patch("tools.actions.get_order_status")
def test_redis_error_becomes_an_error_result(mock_status):
    mock_status.return_value = STUCK
    r = Mock()
    r.xadd.side_effect = redis.ConnectionError("down")
    assert "could not publish" in republish_order_placed("1", r=r)["error"]