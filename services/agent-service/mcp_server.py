import os
from mcp.server.mcpserver import MCPServer

from tools.events import get_order_events as read_order_events
from tools.orders import get_order_status as read_order_status

mcp = MCPServer("hkhr-store")


@mcp.tool()
def get_order_status(order_id: str) -> dict:
    """Get the current status of one order from order-service. Read-only."""
    return read_order_status(order_id)


@mcp.tool()
def get_order_events(order_id: str) -> dict:
    """List the events recorded for one order, in time order. Read-only."""
    return read_order_events(order_id)


if __name__ == "__main__":
    if os.environ.get("MCP_TRANSPORT") == "http":
        mcp.run(transport="streamable-http", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
    else:
        mcp.run(transport="stdio")