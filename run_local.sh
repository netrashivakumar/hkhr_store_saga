#!/usr/bin/env bash
# Starts all services locally.
#   REDIS_URL     required (Upstash URL)
#   DATABASE_URL  one Postgres URL used by all three DB services (fine locally:
#                 the tables don't collide), OR set ORDERS_DATABASE_URL,
#                 INVENTORY_DATABASE_URL and PAYMENTS_DATABASE_URL separately.
set -e
: "${REDIS_URL:?Export REDIS_URL first, e.g. rediss://default:PASSWORD@host.upstash.io:6379}"
ORDERS_DB="${ORDERS_DATABASE_URL:-${DATABASE_URL:-}}"
INVENTORY_DB="${INVENTORY_DATABASE_URL:-${DATABASE_URL:-}}"
PAYMENTS_DB="${PAYMENTS_DATABASE_URL:-${DATABASE_URL:-}}"
: "${ORDERS_DB:?Export DATABASE_URL (or the three *_DATABASE_URL variables)}"
: "${INVENTORY_DB:?Export DATABASE_URL (or the three *_DATABASE_URL variables)}"
: "${PAYMENTS_DB:?Export DATABASE_URL (or the three *_DATABASE_URL variables)}"

pip install -q -r services/order-service/requirements.txt \
                -r services/frontend/requirements.txt

trap 'kill 0' EXIT

(cd services/order-service       && PORT=5001 DATABASE_URL="$ORDERS_DB"    python app.py) &
sleep 3   # let order-service create its tables first
(cd services/inventory-service   && PORT=5002 DATABASE_URL="$INVENTORY_DB" python worker.py) &
(cd services/payment-service     && PORT=5004 DATABASE_URL="$PAYMENTS_DB"  python worker.py) &
(cd services/notification-worker && PORT=5003 python worker.py) &
(cd services/frontend            && PORT=5000 ORDER_API_URL=http://localhost:5001 python app.py) &

wait
