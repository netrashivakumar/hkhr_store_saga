"""Mock tests: events.py retry / dead-letter / reclaim logic with a fake Redis."""
import json
from unittest.mock import MagicMock

import events


def msg(payload):
    return {"payload": json.dumps(payload)}


def test_successful_handler_is_acked():
    r, handler = MagicMock(), MagicMock()

    events._process(r, "g", "s", "1-0", msg({"a": 1}), handler)

    handler.assert_called_once_with({"a": 1})
    r.xack.assert_called_once_with("s", "g", "1-0")


def test_first_failure_is_left_pending_for_retry():
    r = MagicMock()
    r.xpending_range.return_value = [{"times_delivered": 1}]
    handler = MagicMock(side_effect=RuntimeError("boom"))

    events._process(r, "g", "s", "1-0", msg({}), handler)

    r.xack.assert_not_called()
    r.xadd.assert_not_called()


def test_missing_pending_info_counts_as_first_delivery():
    r = MagicMock()
    r.xpending_range.return_value = []
    handler = MagicMock(side_effect=RuntimeError("boom"))

    events._process(r, "g", "s", "1-0", msg({}), handler)

    r.xack.assert_not_called()
    r.xadd.assert_not_called()


def test_failure_at_max_deliveries_goes_to_dead_letter_and_is_acked():
    r = MagicMock()
    r.xpending_range.return_value = [{"times_delivered": events.MAX_DELIVERIES}]
    handler = MagicMock(side_effect=RuntimeError("boom"))
    data = msg({"order_id": "o-1"})

    events._process(r, "g", "s", "1-0", data, handler)

    args, _ = r.xadd.call_args
    assert args[0] == events.DEAD_LETTER_STREAM
    assert args[1]["source_stream"] == "s"
    assert args[1]["group"] == "g"
    assert args[1]["error"] == "boom"
    assert args[1]["payload"] == data["payload"]       # original message preserved
    r.xack.assert_called_once_with("s", "g", "1-0")


def test_long_error_messages_are_truncated_to_500_chars():
    r = MagicMock()
    r.xpending_range.return_value = [{"times_delivered": events.MAX_DELIVERIES}]
    handler = MagicMock(side_effect=RuntimeError("x" * 2000))

    events._process(r, "g", "s", "1-0", msg({}), handler)

    assert len(r.xadd.call_args.args[1]["error"]) == 500


def test_poison_message_with_invalid_json_is_dead_lettered_not_crashing():
    r = MagicMock()
    r.xpending_range.return_value = [{"times_delivered": events.MAX_DELIVERIES}]
    handler = MagicMock()

    events._process(r, "g", "s", "1-0", {"payload": "not json"}, handler)

    handler.assert_not_called()
    assert r.xadd.call_args.args[0] == events.DEAD_LETTER_STREAM
    r.xack.assert_called_once()


def test_reclaim_retries_stuck_messages_and_skips_empty_ones():
    r = MagicMock()
    r.xautoclaim.return_value = ("0-0", [("1-0", msg({"x": 1})), ("2-0", {})])
    handler = MagicMock()

    events._reclaim(r, "g", "c", {"s": handler})

    handler.assert_called_once_with({"x": 1})
    assert r.xautoclaim.call_args.kwargs["min_idle_time"] == events.RECLAIM_IDLE_MS
