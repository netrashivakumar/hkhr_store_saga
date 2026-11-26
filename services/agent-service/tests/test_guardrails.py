import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.loop import run_agent


def text_response(text):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(stop_reason="end_turn", content=[block])


def tool_response(name, arguments):
    block = SimpleNamespace(type="tool_use", id="tool_1", name=name, input=arguments)
    return SimpleNamespace(stop_reason="tool_use", content=[block])


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def send(self, system, messages, tools):
        self.calls.append(list(messages))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def audit_file(tmp_path, monkeypatch):
    path = tmp_path / "audit.jsonl"
    monkeypatch.setattr("agent.guardrails.AUDIT_LOG", path)
    return path


@patch("agent.loop.run_tool")
def test_denied_write_does_not_run(mock_run_tool, audit_file):
    client = FakeClient([
        tool_response("republish_order_placed", {"order_id": "1"}),
        text_response("Not done."),
    ])
    run_agent("Retry order 1", client, approver=lambda name, args: False)
    mock_run_tool.assert_not_called()
    result = client.calls[1][-1]["content"][0]["content"]
    assert "denied" in result
    assert '"approved": false' in audit_file.read_text()


@patch("agent.loop.run_tool")
def test_approved_write_runs(mock_run_tool, audit_file):
    mock_run_tool.return_value = {"ok": True}
    client = FakeClient([
        tool_response("republish_order_placed", {"order_id": "1"}),
        text_response("Done."),
    ])
    run_agent("Retry order 1", client, approver=lambda name, args: True)
    mock_run_tool.assert_called_once_with("republish_order_placed", {"order_id": "1"})
    assert '"event": "executed"' in audit_file.read_text()


@patch("agent.loop.run_tool")
def test_read_tool_needs_no_approval(mock_run_tool):
    mock_run_tool.return_value = {"status": "FAILED"}

    def never(name, args):
        raise AssertionError("approval must not be asked for a read tool")

    client = FakeClient([
        tool_response("get_order_status", {"order_id": "1"}),
        text_response("Done."),
    ])
    assert run_agent("Status?", client, approver=never) == "Done."