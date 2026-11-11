# 🛒 hkhr_store: Event-Driven Microservices with a Saga

Five small services, each with its **own responsibility and its own database**,
cooperating only through **events** on Upstash Redis Streams. The services are
packaged as Docker images, published to GitHub Container Registry (GHCR) and run
either with Docker Compose or on Kubernetes.

## The order saga (choreography)

```text
 Browser ──POST /api/order──> order-service ──(orders DB: PENDING)
                                   │ OrderPlaced
                                   ▼
                          inventory-service ──(inventory DB: reserve stock)
                           │ StockReserved            │ StockRejected ──────┐
                           ▼                          │                     │
                    payment-service ──(payments DB)   │                     │
                     │ PaymentConfirmed │ PaymentFailed                     │
                     │                  ├──> inventory-service releases     │
                     │                  │    the stock (compensation)       │
                     ▼                  ▼                                   ▼
                              order-service updates its row
                          OrderCompleted          OrderFailed
                                   └────────┬────────┘
                                            ▼
                                   notification-worker
```

| Event | Stream | Published by | Consumed by |
|---|---|---|---|
| OrderPlaced | `order_placed` | order-service | inventory-service |
| StockReserved | `stock_reserved` | inventory-service | payment-service, order-service |
| StockRejected | `stock_rejected` | inventory-service | order-service |
| PaymentConfirmed | `payment_confirmed` | payment-service | order-service |
| PaymentFailed | `payment_failed` | payment-service | order-service, inventory-service |
| OrderCompleted | `order_completed` | order-service | notification-worker |
| OrderFailed | `order_failed` | order-service | notification-worker |
| (poison messages) | `dead_letter` | any consumer | you, for inspection |

Order status in the orders DB moves `PENDING → STOCK_RESERVED → COMPLETED` or `FAILED`.

## Services and databases

| Service | Folder | Database | Start command | Port |
|---|---|---|---|---|
| frontend | `services/frontend` | none | `gunicorn app:app` | 5000 |
| order-service | `services/order-service` | `orders` table | `gunicorn app:app --workers 1 --threads 4` | 5001 |
| inventory-service | `services/inventory-service` | `stock`, `reservations` | `python worker.py` | 5002 |
| payment-service | `services/payment-service` | `payments` | `python worker.py` | 5004 |
| notification-worker | `services/notification-worker` | none | `python worker.py` | 5003 |

The port is read from the `PORT` environment variable. Only the frontend and
order-service are reached from a browser; the workers just consume events.

`events.py` and `db.py` are intentionally **copied** into each service: services
never import each other's code.

## Tech stack

| Layer | Technology | Role |
|---|---|---|
| Services | Python 3.12, Flask, gunicorn, flask-cors | Web services and event workers |
| Events | Redis Streams on **Upstash** | Event bus between services |
| Data | PostgreSQL on **Neon**, psycopg2 | One set of tables per service |
| Packaging | Docker, Docker Compose | One image per service, one command to run all |
| Registry | **GHCR** (`ghcr.io`) | Stores the five images |
| Orchestration | Kubernetes (**kind** locally), kubectl, Kustomize | Runs the containers, base manifests plus overlays |
| Source and CI | Git, GitHub, GitHub Actions, Codespaces | Code, tests on each push, dev environment |
| Delivery (in progress) | Jenkins | Build, push and deploy on each push |

## Repository layout

```text
hkhr_store_saga/
├── .github/workflows/cicd.yml     # GitHub Actions: tests and checks
├── docker-compose.yml             # run all five services together
├── .env.example                   # variable names with fake values (committed)
├── .env                           # real values, gitignored, never commit
├── run_local.sh                   # run everything without containers
├── services/
│   ├── frontend/                  # app.py, templates/, Dockerfile
│   ├── order-service/             # app.py, db.py, events.py, Dockerfile
│   ├── inventory-service/         # worker.py, db.py, events.py, Dockerfile
│   ├── payment-service/           # worker.py, db.py, events.py, Dockerfile
│   └── notification-worker/       # worker.py, events.py, Dockerfile
├── k8s/
│   ├── base/                      # kustomization.yaml, frontend.yaml, order-service.yaml, workers.yaml
│   └── overlays/
│       ├── staging/               # kustomization.yaml (namespace: staging)
│       └── production/            # kustomization.yaml (namespace: production)
└── jenkins/                       # Dockerfile for a Jenkins image with Docker and kubectl (in progress)
```

Each service folder also has a `.dockerignore`, `requirements.txt`, and tests.

## Configuration

Configuration is by environment variables. Keep real values in `.env` (gitignored)
and copy the names from `.env.example`.

| Variable | Used by | Meaning |
|---|---|---|
| `REDIS_URL` | all services except frontend | Upstash TCP URL, `rediss://default:PASSWORD@host.upstash.io:6379` (`rediss` = TLS) |
| `DATABASE_URL` | order, inventory, payment | Neon URL, `postgresql://user:password@host/db?sslmode=require` |
| `ORDERS_DATABASE_URL`, `INVENTORY_DATABASE_URL`, `PAYMENTS_DATABASE_URL` | Compose and `run_local.sh` | Optional per-service databases. Each falls back to `DATABASE_URL` |
| `ORDER_API_URL` | frontend | Address of order-service **as the browser reaches it** |
| `ALLOWED_ORIGINS` | order-service | The frontend address allowed to call the API (CORS) |
| `PORT` | all | Port to listen on |
| `PAYMENT_LIMIT` | payment-service | Optional, default 1000 |

In Codespaces the browser needs the forwarded addresses, not `localhost`:

```text
ORDER_API_URL=https://<codespace-name>-5001.app.github.dev
ALLOWED_ORIGINS=https://<codespace-name>-5000.app.github.dev
```

Use no trailing slash. The order-service port (5001) must be **Public** in the
Codespaces Ports tab while you test, because the browser calls it directly.

> **Gotcha:** a variable exported in your terminal beats `.env`. If you see
> `password authentication failed` after changing a password, run
> `unset DATABASE_URL INVENTORY_DATABASE_URL ORDERS_DATABASE_URL PAYMENTS_DATABASE_URL REDIS_URL`
> and then `docker compose down` and `docker compose up --build`.

## 1. Create the data stores

- **Neon:** create a project and three databases `orders_db`, `inventory_db`, `payments_db`
  (one database also works: the table names don't collide). Copy the connection string,
  using the pooled one if offered.
- **Upstash:** create a Redis database and copy the **TCP** connection string
  (not the REST URL).

## 2. Run locally

### Option A: without containers (Codespaces)

```bash
export REDIS_URL="rediss://default:PASSWORD@your-endpoint.upstash.io:6379"
export DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require"   # same URL for all, locally
./run_local.sh
```

Open port 5000 and place orders. Watch the terminal for `[inventory]`, `[payment]`, `[notification]` lines.

### Option B: Docker Compose

```bash
cp .env.example .env        # then edit .env with your real values
docker compose up --build   # add -d to run in the background
docker compose ps           # status of the five services
docker compose logs -f order-service
docker compose down         # stop and remove (run this after changing .env)
```

Open port 5000 and place an order. The compose file maps `5000:5000` (frontend) and
`5001:5001` (order-service) and starts the workers after order-service, which creates the tables.

Build notes:

- The images use `python:3.12-slim`. `psycopg2-binary` has no prebuilt wheel for Python 3.14,
  so a 3.14 base image fails with `pg_config executable not found`.
- Each Dockerfile copies `requirements.txt` first so dependency installs are cached,
  runs as a non-root user, and web services start with
  `gunicorn --bind 0.0.0.0:${PORT} app:app`.

## 3. Container images (GHCR)

Images are published to GitHub Container Registry, all tagged `dev`:

```text
ghcr.io/netrashivakumar/hkhr-frontend:dev
ghcr.io/netrashivakumar/hkhr-order-service:dev
ghcr.io/netrashivakumar/hkhr-inventory-service:dev
ghcr.io/netrashivakumar/hkhr-payment-service:dev
ghcr.io/netrashivakumar/hkhr-notification-worker:dev
```

Publish them from the images Compose builds:

```bash
# one-time: create a classic token with only the write:packages scope
read -rs GHCR_TOKEN
echo "${#GHCR_TOKEN}"        # a classic token is 40 characters
echo "$GHCR_TOKEN" | docker login ghcr.io -u netrashivakumar --password-stdin
unset GHCR_TOKEN

for svc in frontend order-service inventory-service payment-service notification-worker; do
  docker tag hkhr_store_saga-$svc:latest ghcr.io/netrashivakumar/hkhr-$svc:dev
  docker push ghcr.io/netrashivakumar/hkhr-$svc:dev
done
```

New packages are private by default. Set each package to **Public**
(profile → Packages → package → Package settings → Danger Zone → Change visibility)
so Kubernetes can pull without a pull secret. Verify anonymously with
`docker logout ghcr.io` followed by `docker pull ghcr.io/netrashivakumar/hkhr-order-service:dev`.

## 4. Kubernetes

Manifests live in `k8s/`. `k8s/base` holds a Deployment per service plus a Service for
the frontend and order-service. The workers have no Service because nothing calls them.
Overlays under `k8s/overlays/` reuse the base and only set the namespace.

### Create a local cluster (kind)

```bash
# install kind once (amd64)
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

kind create cluster --name hkhr
kubectl config current-context     # kind-hkhr
kubectl get nodes                  # hkhr-control-plane   Ready
```

### Create the Secret and ConfigMap (per namespace)

These are created from `.env` and are never committed. `grep` and `cut` are used
instead of `source` because the `&` in the Neon URL breaks the shell.

```bash
REDIS_URL=$(grep '^REDIS_URL=' .env | cut -d= -f2-)
DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
ORDER_API_URL=$(grep '^ORDER_API_URL=' .env | cut -d= -f2-)
ALLOWED_ORIGINS=$(grep '^ALLOWED_ORIGINS=' .env | cut -d= -f2-)

kubectl create namespace staging
kubectl -n staging create secret generic hkhr-secrets --from-literal=REDIS_URL="$REDIS_URL" --from-literal=DATABASE_URL="$DATABASE_URL"
kubectl -n staging create configmap hkhr-config --from-literal=ORDER_API_URL="$ORDER_API_URL" --from-literal=ALLOWED_ORIGINS="$ALLOWED_ORIGINS"

unset REDIS_URL DATABASE_URL ORDER_API_URL ALLOWED_ORIGINS
```

Repeat with `production` when that environment is deployed.

### Deploy and use

```bash
kubectl apply -k k8s/overlays/staging
kubectl get pods -n staging -w                 # wait for 1/1 Running
kubectl logs deploy/order-service -n staging --tail=5

kubectl port-forward -n staging svc/frontend 5000:5000 > /tmp/pf-frontend.log 2>&1 &
kubectl port-forward -n staging svc/order-service 5001:5001 > /tmp/pf-order.log 2>&1 &
pkill -f "kubectl port-forward"                # when you are done
```

> **Shared data:** every environment (Compose, local scripts, staging, production) currently
> talks to the same Upstash Redis and Neon database. Do not run two copies of the workers at
> once, or they compete for the same events. Give staging and production separate databases
> or key prefixes before treating them as real environments.

## 5. CI/CD

- **GitHub Actions** (`.github/workflows/cicd.yml`, "CI/CD Pipeline") runs the tests on pushes
  and pull requests.
- **Branches:** work on `dev`, open a pull request into `main` once CI is green.
- **Jenkins (in progress):** a Jenkins container with the Docker CLI and kubectl
  (`jenkins/Dockerfile`) will run a Multibranch Pipeline. The plan is: test, build the images,
  push to GHCR, then `kubectl apply -k` the staging overlay for `dev` and the production
  overlay for `main` after a manual approval.

## 6. Deploy on Render (original free hosting option)

Create one **Web Service** per row (same repo, set **Root Directory**, build command `pip install -r requirements.txt`).
Create the three workers first so you have their URLs.

| Service | Root Directory | Env vars |
|---|---|---|
| inventory-service | `services/inventory-service` | `REDIS_URL`, `DATABASE_URL` (inventory db) |
| payment-service | `services/payment-service` | `REDIS_URL`, `DATABASE_URL` (payments db), optional `PAYMENT_LIMIT` (default 1000) |
| notification-worker | `services/notification-worker` | `REDIS_URL` |
| order-service | `services/order-service` | `REDIS_URL`, `DATABASE_URL` (orders db), `WAKE_URLS` (the three worker URLs, comma-separated), `ALLOWED_ORIGINS` (frontend URL) |
| frontend | `services/frontend` | `ORDER_API_URL` (order-service URL) |

**Why `WAKE_URLS`?** Free Render services sleep after ~15 minutes without HTTP traffic,
and a sleeping worker can't read its stream. When an order is accepted, order-service
pings the workers so they wake up and process the backlog. The first order after idle
time can therefore take about a minute.

## Things to try

| Order | What happens |
|---|---|
| Phone × 1 | Stock reserved → payment confirmed → **COMPLETED** |
| Laptop × 6 | Only 5 in stock → `StockRejected` → **FAILED** |
| Laptop × 2 | $1800 exceeds the $1000 limit → `PaymentFailed` → stock **released** → **FAILED** |

Then check the tables in Neon and the streams in Upstash's Data Browser.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `unknown instruction` when building a Dockerfile | Stray text or a trailing `EOF` ended up inside the file | Open the Dockerfile and delete everything after the last instruction |
| `pg_config executable not found` during `pip install` | Python 3.14 base image, no wheel for `psycopg2-binary` | Use `python:3.12-slim` |
| `password authentication failed` after resetting a password | An old `DATABASE_URL` is exported in the shell | `unset` the variables, `docker compose down`, then `up --build` |
| Page loads but placing an order fails in the browser | `ORDER_API_URL` or `ALLOWED_ORIGINS` wrong, or port 5001 private | Use the forwarded addresses, no trailing slash, set 5001 Public |
| `docker login` says `denied` | Token empty, too long (extra text pasted) or missing `write:packages` | Re-enter the token, check its length is 40 |
| `not found` pulling an image from GHCR | Tag not pushed, or package private | Push again and set the package to Public |
| `kubectl` says `localhost:8080 refused` | No cluster exists | `kind create cluster --name hkhr` |
| Pod stuck in `ImagePullBackOff` | Image missing or private | Check the image name and that the package is Public |

## Security notes

- Never commit `.env`. It is in `.gitignore`; check `git status --short` before each commit.
- Treat the Upstash password, the Neon password and GitHub tokens as secrets. If one appears in
  a screenshot, chat or log, reset it once the project holds real data.
- Mounting the Docker socket into Jenkins gives it full control of the host's Docker. Do this only
  in a throwaway development environment.

## Status

| Step | State |
|---|---|
| Saga services, tests and GitHub Actions CI | Done |
| Dockerfiles and Docker Compose | Done |
| Images in GHCR, public | Done |
| kind cluster and base manifests | Done |
| Staging overlay deployed | Deployed in the `staging` namespace |
| Production overlay | Defined, not deployed |
| Separate data for staging and production | To do |
| Jenkins image, Jenkinsfile and pipeline | In progress |

## Concepts this project demonstrates

- **Database per service**: no service reads another service's tables.
- **Saga (choreography)**: a business transaction spread across services with no central coordinator.
- **Compensating transaction**: `PaymentFailed` makes inventory release the stock.
- **Idempotent consumers**: duplicate deliveries don't double-reserve or double-charge
  (unique `order_id` keys, status checks).
- **At-least-once delivery**: consumer groups + ack + retry after 30s + dead-letter stream.
- **Containers and orchestration**: one image per service, the same images run under Compose
  and Kubernetes, configuration injected through environment variables, Secrets and ConfigMaps.
- **Known limitation, the dual-write problem**: a service commits to its DB and then publishes.
  A crash in between is repaired by re-publishing on redelivery here, but production systems
  use the **transactional outbox pattern**. A good next exercise.
