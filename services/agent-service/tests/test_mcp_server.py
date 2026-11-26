from unittest.mock import patch

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        yield c


@pytest.mark.anyio
async def test_lists_both_tools(client):
    result = await client.list_tools()
    names = sorted(tool.name for tool in result.tools)
    assert names == ["get_order_events", "get_order_status"]


@pytest.mark.anyio
@patch("mcp_server.read_order_status")
async def test_status_tool_runs_the_function(mock_read, client):
    mock_read.return_value = {"order_id": "123", "status": "FAILED"}
    result = await client.call_tool("get_order_status", {"order_id": "123"})
    mock_read.assert_called_once_with("123")
    assert "FAILED" in result.content[0].text


@pytest.mark.anyio
@patch("mcp_server.read_order_events")
async def test_events_tool_runs_the_function(mock_read, client):
    mock_read.return_value = {"order_id": "123", "events": []}
    result = await client.call_tool("get_order_events", {"order_id": "123"})
    mock_read.assert_called_once_with("123")
    assert "123" in result.content[0].text