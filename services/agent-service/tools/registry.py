from tools.actions import republish_order_placed
from tools.events import get_order_events
from tools.orders import get_order_status
from tools.runbook import search_runbook

ORDER_ID_SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "string", "description": "The order ID"},
    },
    "required": ["order_id"],
}

# Tool descriptions sent to Claude so it knows what it can call.
TOOLS = [
    {
        "name": "get_order_status",
        "description": (
            "Get the current status of one order from order-service. "
            "Read-only. Returns the order data, or an error."
        ),
        "input_schema": ORDER_ID_SCHEMA,
    },
    {
        "name": "get_order_events",
        "description": (
            "List the events recorded for one order, in time order, such as "
            "order placed, stock reserved, payment failed, order failed. "
            "Use it to see what happened step by step. "
            "Read-only. Returns the events, or an error."
        ),
        "input_schema": ORDER_ID_SCHEMA,
    },
    {
        "name": "search_runbook",
        "description": (
            "Search the store's runbook for how to handle a failure or a "
            "stuck order, and what is safe to do. Read-only. Use it before "
            "suggesting what to do."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up, in a few words"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "republish_order_placed",
        "description": (
            "WRITE action: publish the OrderPlaced event again to retry an "
            "order that is stuck in PENDING or STOCK_RESERVED. Completed and "
            "failed orders are refused. A human must approve every use."
        ),
        "input_schema": ORDER_ID_SCHEMA,
    },
]

TOOL_FUNCTIONS = {
    "get_order_status": get_order_status,
    "get_order_events": get_order_events,
    "search_runbook": search_runbook,
    "republish_order_placed": republish_order_placed,
}


def run_tool(name, arguments):
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"unknown tool: {name}"}
    return function(**arguments)