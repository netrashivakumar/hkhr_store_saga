"""Event plumbing. This file is copied into every service on purpose:
services never import each other's code, so each keeps its own copy.
"""
import json
import os
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import redis

DEAD_LETTER_STREAM = "dead_letter"
MAX_DELIVERIES = 3          # failed attempts before a message goes to dead letter
RECLAIM_IDLE_MS = 30000     # a pending message idle this long gets retried
RECLAIM_EVERY_S = 60        # how often to look for stuck messages
BLOCK_MS = 20000            # long blocking read keeps Redis command usage low


def log(message):
    print(message, flush=True)


def get_redis():
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    return redis.Redis.from_url(url, decode_responses=True,
                                health_check_interval=30)


def publish(r, stream, event_type, payload):
    """Append an event to a stream. One stream per event type."""
    return r.xadd(stream, {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": str(int(time.time())),
        "payload": json.dumps(payload),
    }, maxlen=10000, approximate=True)


def _process(r, group, stream, msg_id, data, handler):
    try:
        handler(json.loads(data["payload"]))
        r.xack(stream, group, msg_id)
    except Exception as exc:  # noqa: BLE001
        log(f"[{group}] handler failed for {stream}/{msg_id}: {exc}")
        pending = r.xpending_range(stream, group, msg_id, msg_id, 1)
        deliveries = pending[0]["times_delivered"] if pending else 1
        if deliveries >= MAX_DELIVERIES:
            r.xadd(DEAD_LETTER_STREAM, {
                **data,
                "source_stream": stream,
                "group": group,
                "error": str(exc)[:500],
            }, maxlen=1000, approximate=True)
            r.xack(stream, group, msg_id)
            log(f"[{group}] moved {stream}/{msg_id} to {DEAD_LETTER_STREAM}")


def _reclaim(r, group, consumer, handlers):
    for stream, handler in handlers.items():
        result = r.xautoclaim(stream, group, consumer,
                              min_idle_time=RECLAIM_IDLE_MS,
                              start_id="0-0", count=10)
        for msg_id, data in result[1]:
            if data:
                _process(r, group, stream, msg_id, data, handler)


def consume(r, service, handlers):
    """Run forever. handlers = {stream_name: function(payload_dict)}.

    Each service uses its own consumer group, so every service receives its
    own copy of every event. Handlers must be idempotent (delivery is
    at-least-once).
    """
    group = f"{service}-group"
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    ready = False
    last_reclaim = 0.0
    while True:
        try:
            if not ready:
                for stream in handlers:
                    try:
                        r.xgroup_create(stream, group, id="0", mkstream=True)
                    except redis.ResponseError as exc:
                        if "BUSYGROUP" not in str(exc):
                            raise
                ready = True
                log(f"[{service}] consuming {list(handlers)} as {consumer}")
            if time.time() - last_reclaim > RECLAIM_EVERY_S:
                _reclaim(r, group, consumer, handlers)
                last_reclaim = time.time()
            response = r.xreadgroup(group, consumer,
                                    {s: ">" for s in handlers},
                                    count=10, block=BLOCK_MS)
            for stream, messages in response or []:
                for msg_id, data in messages:
                    _process(r, group, stream, msg_id, data, handlers[stream])
        except redis.RedisError as exc:
            log(f"[{service}] redis error: {exc}")
            time.sleep(5)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def start_health_server(default_port):
    """Tiny HTTP server so a worker can run as a free Render Web Service."""
    port = int(os.environ.get("PORT", default_port))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
