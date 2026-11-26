import json
import os
import time
import uuid

import redis

from tools.events import get_redis
from tools.orders import get_order_status

# Only orders that are still in progress can be retried.
RETRYABLE = {"PENDING", "STOCK_RESERVED"}


def republish_order_placed(order_id, r=None):
    """WRITE tool: publish OrderPlaced again for a stuck order."""
    order = get_order_status(order_id)
    if "error" in order:
        return order
    if order.get("status") not in RETRYABLE:
        return {"error": f"order is {order.get('status')}; only PENDING or "
                         "STOCK_RESERVED orders can be retried"}
    try:
        r = r or get_redis()
        prefix = os.environ.get("STREAM_PREFIX", "")
        message_id = r.xadd(prefix + "order_placed", {
            "event_id": str(uuid.uuid4()),
            "event_type": "OrderPlaced",
            "occurred_at": str(int(time.time())),
            "payload": json.dumps({
                "order_id": order_id,
                "item": order["item"],
                "quantity": order["quantity"],
            }),
        }, maxlen=10000, approximate=True)
    except (KeyError, redis.RedisError) as error:
        return {"error": f"could not publish: {error}"}
    return {"republished": order_id, "message_id": message_id}