"""Mock test: main() connects the right streams to the right handlers.

Catches typos in stream names, which would silently stop notifications
(see the event table in the README).
"""
import worker


def test_main_wires_streams_to_handlers(monkeypatch):
    seen = {}
    monkeypatch.setattr(worker.events, "start_health_server",
                        lambda port: seen.update(port=port))
    monkeypatch.setattr(worker.events, "consume",
                        lambda r, service, handlers: seen.update(
                            r=r, service=service, handlers=handlers))

    worker.main()

    assert seen["port"] == 5003
    assert seen["service"] == "notification-worker"
    assert seen["r"] is worker.r
    assert seen["handlers"] == {
        "order_completed": worker.on_order_completed,
        "order_failed": worker.on_order_failed,
    }
