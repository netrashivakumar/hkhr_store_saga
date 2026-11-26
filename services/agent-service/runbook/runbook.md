# hkhr store runbook

## Payment failed over the limit
Orders above the payment limit fail on purpose. The limit is 1000 by default (PAYMENT_LIMIT in payment-service). The events show OrderPlaced, StockReserved, PaymentFailed, OrderFailed. No action is needed: the customer must order a smaller amount. Do not retry, because a retry fails the same way.

## Insufficient stock
If the quantity is more than the stock, inventory-service publishes StockRejected and the order fails with OrderFailed. No payment is attempted. No action is needed unless the stock should be refilled.

## Order stuck after stock reserved
The last event is StockReserved and no PaymentConfirmed or PaymentFailed follows. First check that payment-service is running (docker compose ps, or kubectl get pods). If it was stopped, start it: it processes the waiting events by itself. If everything is running, retry with republish_order_placed, which needs a human's approval. Only PENDING and STOCK_RESERVED orders can be retried.

## Order stuck in pending
The last event is OrderPlaced. Check that inventory-service is running and look at the dead_letter stream. A retry with republish_order_placed is allowed after approval.

## Was the stock released after a payment failure
Inventory-service releases the stock after PaymentFailed, but it publishes no event for it, so the events cannot prove it. Say so, and do not claim the stock is still reserved. Confirming needs inventory data.

## Duplicate events after a retry
A retry sends the whole chain twice. Payments and reservations stay at one row each, because the consumers are idempotent. The notification worker can send two confirmations. This is known and does not harm the data.

## Dead letter stream
Events that failed three times are copied to the dead_letter stream with the error text. Inspect them. A dead letter can come from a bad event or from a service that was down. Do not replay them blindly.