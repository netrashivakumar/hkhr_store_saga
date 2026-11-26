import json
import os
from datetime import datetime, timezone

import redis

EVENT_STREAMS = [
    "order_placed", "stock_reserved", "stock_rejected",
    "payment_confirmed", "payment_failed",
    "order_completed", "order_failed", "dead_letter",
]


def get_redis():
    return redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def get_order_events(order_id, r=None):
    """Read-only: list the events in the Redis streams that mention one order."""
    prefix = os.environ.get("STREAM_PREFIX", "")
    found = []
    try:
        r = r or get_redis()
        for name in EVENT_STREAMS:
            for _, data in r.xrevrange(prefix + name, count=500):
                if order_id not in data.get("payload", ""):
                    continue
                event = {
                    "stream": name,
                    "event_type": data.get("event_type"),
                    "occurred_at": datetime.fromtimestamp(
                        int(data["occurred_at"]), timezone.utc).isoformat(),
                    "payload": json.loads(data["payload"]),
                }
                if "error" in data:
                    event["error"] = data["error"]
                found.append(event)
    except (KeyError, ValueError, redis.RedisError) as error:
        return {"error": f"could not read events: {error}"}
    found.sort(key=lambda e: e["occurred_at"])
    return {"order_id": order_id, "events": found}