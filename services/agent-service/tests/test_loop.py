from types import SimpleNamespace
from unittest.mock import patch

from agent.loop import MAX_STEPS, run_agent


def text_response(text):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(stop_reason="end_turn", content=[block])


def tool_response(name, arguments, tool_id="tool_1"):
    block = SimpleNamespace(type="tool_use", id=tool_id, name=name, input=arguments)
    return SimpleNamespace(stop_reason="tool_use", content=[block])


class FakeClient:
    """Returns scripted responses, one per call. No network, no cost."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def send(self, system, messages, tools):
        self.calls.append(list(messages))
        return self.responses.pop(0)


def test_answers_without_tools():
    client = FakeClient([text_response("All good.")])
    assert run_agent("Hi", client) == "All good."


@patch("agent.loop.run_tool")
def test_runs_tool_then_answers(mock_run_tool):
    mock_run_tool.return_value = {"status": "FAILED"}
    client = FakeClient([
        tool_response("get_order_status", {"order_id": "123"}),
        text_response("Order 123 failed."),
    ])
    answer = run_agent("What happened to order 123?", client)
    assert answer == "Order 123 failed."
    mock_run_tool.assert_called_once_with("get_order_status", {"order_id": "123"})
    # the second call to Claude must include the tool result
    result_block = client.calls[1][-1]["content"][0]
    assert result_block["type"] == "tool_result"
    assert "FAILED" in result_block["content"]


@patch("agent.loop.run_tool")
def test_stops_after_max_steps(mock_run_tool):
    mock_run_tool.return_value = {"status": "FAILED"}
    client = FakeClient(
        [tool_response("get_order_status", {"order_id": "1"})] * MAX_STEPS
    )
    assert run_agent("Loop forever", client) == "Stopped: too many steps."
    assert len(client.calls) == MAX_STEPS