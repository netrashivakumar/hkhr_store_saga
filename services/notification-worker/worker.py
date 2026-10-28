"""notification-worker: stateless. Tells the customer how the order ended.

Consumes: OrderCompleted, OrderFailed
"""
import events

r = events.get_redis()


def on_order_completed(p):
    # Replace this log line with a real email/SMS provider call.
    events.log(f"[notification] ✅ Confirmation sent: order {p['order_id']} "
               f"({p['quantity']} x {p['item']}, total ${p['amount']:.2f})")


def on_order_failed(p):
    events.log(f"[notification] ❌ Failure notice sent: order "
               f"{p['order_id']} - {p['reason']}")


def main():
    events.start_health_server(5003)
    events.consume(r, "notification-worker", {
        "order_completed": on_order_completed,
        "order_failed": on_order_failed,
    })


if __name__ == "__main__":
    main()
