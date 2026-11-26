from types import SimpleNamespace

import pytest

from agent.observability import RunStats


def test_adds_up_tokens_and_cost():
    stats = RunStats()
    usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000)
    stats.add_response(SimpleNamespace(usage=usage))
    assert stats.steps == 1
    assert stats.cost == pytest.approx(0.60)


def test_summary_counts_tool_errors(capsys):
    stats = RunStats()
    stats.add_tool_call("get_order_status", 0.1, failed=True)
    stats.add_tool_call("get_order_events", 0.2, failed=False)
    stats.print_summary()
    out = capsys.readouterr().out
    assert "tool_calls=2" in out
    assert "tool_errors=1" in out