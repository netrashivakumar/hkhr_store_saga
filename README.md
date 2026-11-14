# 🛒 hkhr_store: Event-Driven Microservices with a Saga

A **full stack**, **cloud-based**, event-driven microservices project: five small services, each with its **own responsibility and its own tables**,
cooperating only through **events** on Upstash Redis Streams. It uses managed **cloud services**
(Neon PostgreSQL, Upstash Redis, GitHub Container Registry, GitHub Actions and Codespaces). The services are
packaged as Docker images, built and deployed by Jenkins, and run with Docker Compose or on Kubernetes
(staging and production namespaces). Everything uses free tiers.

## About this project

hkhr_store_saga is a **prototype**, built to demonstrate how a full stack,
event-driven system fits together. It is deliberately small: each technology is used
for real and works end to end, but the store itself is minimal.

**What it is not:** a finished online store. Payments follow a simple simulated rule
(an order over a limit fails) rather than a real payment provider, and there is no
user login, cart or product catalog.

**What it is:** a working example of the architecture and tooling a real store could be
built on, and a place to practice them.

### Technologies used

| Area | Technologies |
|---|---|
| Language and web | Python 3.12, Flask, gunicorn, flask-cors |
| Events | Redis Streams on Upstash |
| Database | PostgreSQL on Neon, psycopg2 |
| Containers | Docker, Docker Compose, GitHub Container Registry (GHCR) |
| Orchestration | Kubernetes (kind), kubectl, Kustomize |
| CI/CD | GitHub Actions, Jenkins |
| Testing and quality | pytest (unit and mock tests), flake8 |
| Development | Git, GitHub, GitHub Codespaces |

### Cloud services used

| Service | Kind | Role |
|---|---|---|
| **Neon** | Managed serverless PostgreSQL | Data layer, one branch per environment |
| **Upstash** | Managed serverless Redis | Event bus (Redis Streams) |
| **GitHub Container Registry (GHCR)** | Cloud container registry | Stores the five service images |
| **GitHub and GitHub Actions** | Cloud source hosting and CI | Code, lint and tests on every push |
| **GitHub Codespaces** | Cloud development environment | Where the project is developed, built and run |

The data store, event broker, image registry, CI and development environment are all cloud
services, and the free tiers cover all of them. The application containers themselves run
on a local kind (Kubernetes in Docker) cluster inside a Codespace, not on managed cloud compute.
Deploying the same images to a hosting platform such as Render, or to managed Kubernetes
(EKS, AKS or GKE), is the natural next step.

### Patterns demonstrated

- **Saga, choreography style:** an order spans several services with no central coordinator.
- **Compensating transactions:** a failed payment releases the reserved stock.
- **Database per service** and **idempotent consumers**.
- **At-least-once delivery** with consumer groups, acknowledgements, retries and a dead-letter stream.
- **Environment isolation:** Neon branches, Kubernetes namespaces and stream prefixes.
- **Gated deployments:** staging on every `dev` build, production after manual approval.

### Growing it into a full store

The structure supports this. Real additions would be user accounts, a product catalog and
cart, a real payment provider, the transactional outbox pattern, a separate message broker
per environment, managed Kubernetes with a secrets manager, and monitoring and alerting.
See [Known limitations](#known-limitations) for the gaps in this version.

## Full stack, by layer

hkhr_store is a **full stack** project: it covers the user interface, the business
logic, the data, and the delivery pipeline that ships it.

| Layer | What it is here | Where it lives |
|---|---|---|
| **Frontend** | A Flask app that serves the store page. The browser loads it from port 5000 and calls order-service directly at `ORDER_API_URL`. | `services/frontend` |
| **Backend** | Four Python services: order-service (HTTP API), plus inventory-service, payment-service and notification-worker, which are event-driven workers. | `services/order-service`, `services/inventory-service`, `services/payment-service`, `services/notification-worker` |
| **Data** | PostgreSQL on Neon (one set of tables per service, one branch per environment) and Redis Streams on Upstash (the event bus). | Neon, Upstash |
| **DevOps** | Docker and Docker Compose, images in GHCR, Kubernetes (kind) with Kustomize overlays, Jenkins for gated deploys, GitHub Actions for lint and tests. | `Dockerfile`s, `docker-compose.yml`, `k8s/`, `Jenkinsfile`, `jenkins/`, `.github/workflows/` |

```text
 Frontend ──> Backend ──> Data          (the application)
     └───────────┴──────────┴──> DevOps (build, test, ship, run)
```

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

Stream names get the optional `STREAM_PREFIX` in front (see
[Environments](#environments)); production uses `prod:`, so its streams are
`prod:order_placed`, `prod:stock_reserved`, and so on.

Order status in the orders DB moves `PENDING → STOCK_RESERVED → COMPLETED` or `FAILED`.

## Services and databases

| Service | Folder | Tables | Start command | Port |
|---|---|---|---|---|
| frontend | `services/frontend` | none | `gunicorn app:app` | 5000 |
| order-service | `services/order-service` | `orders` | `gunicorn app:app --workers 1 --threads 4` | 5001 |
| inventory-service | `services/inventory-service` | `stock`, `reservations` | `python worker.py` | 5002 |
| payment-service | `services/payment-service` | `payments` | `python worker.py` | 5004 |
| notification-worker | `services/notification-worker` | none | `python worker.py` | 5003 |

The port is read from the `PORT` environment variable. Only the frontend and
order-service are reached from a browser; the workers just consume events.

order-service also exposes `GET /api/order/<order_id>` (status) and `GET /health`.

`events.py` and `db.py` are intentionally **copied** into each service: services
never import each other's code.

## Tech stack

| Layer | Technology | Role |
|---|---|---|
| Services | Python 3.12, Flask, gunicorn, flask-cors | Web services and event workers |
| Events | Redis Streams on **Upstash** | Event bus between services |
| Data | PostgreSQL on **Neon**, psycopg2 | One set of tables per service, one Neon branch per environment |
| Packaging | Docker, Docker Compose | One image per service, one command to run all |
| Registry | **GHCR** (`ghcr.io`) | Stores the five images |
| Orchestration | Kubernetes (**kind** locally), kubectl, Kustomize | Runs the containers, base manifests plus overlays |
| Source and CI | Git, GitHub, GitHub Actions, Codespaces | Code, tests on each push, dev environment |
| Delivery | **Jenkins** (multibranch pipeline in Docker) | Test, build, push and deploy on each push |
| Tests | pytest | Unit tests and mock tests per service |

## Repository layout

```text
hkhr_store_saga/
├── .github/workflows/cicd.yml     # GitHub Actions: lint and tests
├── Jenkinsfile                    # multibranch pipeline (test, build, push, deploy)
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
│       ├── staging/               # kustomization.yaml (namespace: staging, hkhr-config generator)
│       └── production/            # kustomization.yaml (namespace: production, STREAM_PREFIX=prod:, hkhr-config generator)
└── jenkins/                       # Dockerfile for a Jenkins image with Docker and kubectl
```

Each service folder also has a `.dockerignore`, `requirements.txt`, `requirements-dev.txt`,
`conftest.py` and a `tests/` folder.

## Environments

| Environment | Where it runs | Neon branch | Namespace | Stream prefix |
|---|---|---|---|---|
| dev | local, Docker Compose, kind | `dev` (default branch) | `default` | none |
| staging | kind cluster | `staging` (auto-delete: Never) | `staging` | none |
| production | kind cluster | `production` (schema-only copy of dev, auto-delete: Never) | `production` | `prod:` |

- **Data is separated by Neon branch.** Each branch has its own copy of the tables in the
  `neondb` database, so staging and production never touch dev's rows.
- **Events are separated by prefix, partially.** The free Upstash plan allows one database,
  so all environments share one Redis. `STREAM_PREFIX` (read in every service's `events.py`,
  set in the production overlay) keeps production's streams apart. Dev and staging both
  use unprefixed streams and therefore share them. Don't run workers for both at the same time.
- The `production` branch was created from `dev` with **Branch schema only** (structure
  without rows). A schema-only branch has no parent in the Neon console. Seed the `stock`
  table before testing the happy path (see [Production](#6-production-deployment)).

## Configuration

Configuration is by environment variables. Keep real values in `.env` (gitignored)
and copy the names from `.env.example`.

| Variable | Used by | Meaning |
|---|---|---|
| `REDIS_URL` | all services except frontend | Upstash TCP URL, `rediss://default:PASSWORD@host.upstash.io:6379` (`rediss` = TLS) |
| `DATABASE_URL` | order, inventory, payment | Neon URL, `postgresql://user:password@host/db?sslmode=require` (use the branch's own URL) |
| `ORDERS_DATABASE_URL`, `INVENTORY_DATABASE_URL`, `PAYMENTS_DATABASE_URL` | Compose and `run_local.sh` | Optional per-service databases. Each falls back to `DATABASE_URL` |
| `ORDER_API_URL` | frontend | Address of order-service **as the browser reaches it** |
| `ALLOWED_ORIGINS` | order-service | The frontend address allowed to call the API (CORS), default `*` |
| `WAKE_URLS` | order-service | Optional comma-separated worker URLs to ping (only needed on free hosts that sleep) |
| `STREAM_PREFIX` | all services | Optional prefix for every stream name, default empty (production: `prod:`) |
| `PORT` | all | Port to listen on |
| `PAYMENT_LIMIT` | payment-service | Optional, default 1000 |

In Kubernetes the variables come from three places:

| Source | Holds |
|---|---|
| Secret `hkhr-secrets` | `DATABASE_URL`, `REDIS_URL` |
| ConfigMap `hkhr-config` | `ORDER_API_URL`, `ALLOWED_ORIGINS`, `WAKE_URLS` |
| Deployment / overlay | `PORT`, `STREAM_PREFIX` |

In Codespaces the browser needs the forwarded addresses, not `localhost`:

```text
ORDER_API_URL=https://<codespace-name>-5001.app.github.dev
ALLOWED_ORIGINS=https://<codespace-name>-5000.app.github.dev
```

Use no trailing slash. The order-service port (5001) must be **Public** in the
Codespaces Ports tab while you test, because the browser calls it directly. Set it
back to Private afterwards.

> **Gotcha:** a variable exported in your terminal beats `.env`. If you see
> `password authentication failed` after changing a password, run
> `unset DATABASE_URL INVENTORY_DATABASE_URL ORDERS_DATABASE_URL PAYMENTS_DATABASE_URL REDIS_URL`
> and then `docker compose down` and `docker compose up --build`.

## 1. Create the data stores

- **Neon:** create a project (`hkhr-store-saga-db`). The default branch is `dev`. Create
  `staging` and `production` branches from it (see [Environments](#environments)). Copy each
  branch's connection string from **Connect** (database `neondb`, role `neondb_owner`),
  using the pooled one if offered.
- **Upstash:** create a Redis database and copy the **TCP** connection string
  (not the REST URL).
- **Reset a password:** Neon, **Roles**, **Reset password** (shown once). Upstash, database
  page, **Reset Credentials**, **Reset**, type the database name. The old password stops
  working immediately, so update every secret and `.env` that uses it, then restart the pods.

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

## 3. Tests

Each backend service has **unit tests** and **mock tests**:

```bash
cd services/<service>
pip install -r requirements-dev.txt
pytest
```

- GitHub Actions runs lint (flake8) and the tests on pushes to `dev` and `main` and on
  pull requests into `main`.
- Deploy pipelines run **only the mock tests**, not the unit tests.

## 4. Container images (GHCR)

Images are published to GitHub Container Registry. Manual builds are tagged `dev`; the
Jenkins pipeline tags each build with the commit:

```text
ghcr.io/netrashivakumar/hkhr-frontend:dev
ghcr.io/netrashivakumar/hkhr-order-service:dev
ghcr.io/netrashivakumar/hkhr-inventory-service:dev
ghcr.io/netrashivakumar/hkhr-payment-service:dev
ghcr.io/netrashivakumar/hkhr-notification-worker:dev
```

Publish them manually from the images Compose builds:

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

## 5. Kubernetes

Manifests live in `k8s/`. `k8s/base` holds a Deployment per service plus a Service for
the frontend and order-service. The workers have no Service because nothing calls them.
Overlays under `k8s/overlays/` reuse the base: staging sets the namespace, production sets
the namespace and `STREAM_PREFIX=prod:`.

### Create a local cluster (kind)

```bash
# install kind once (amd64)
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

kind create cluster --name hkhr
kubectl config use-context kind-hkhr
kubectl get nodes                  # hkhr-control-plane   Ready
kubectl create namespace staging
kubectl create namespace production
```

### Create the Secret (per namespace)

The Secret is **not** stored in git and disappears if the cluster is rebuilt, so recreate it
after a rebuild. The ConfigMap `hkhr-config` is generated by each overlay (`configMapGenerator`),
so edit the literals there and redeploy to change it. Pods read both only at startup, so run
`kubectl -n <ns> rollout restart deployment` after changing the Secret.

Staging, from `.env` (`grep` and `cut` are used instead of `source` because the `&` in the
Neon URL breaks the shell):

```bash
REDIS_URL=$(grep '^REDIS_URL=' .env | cut -d= -f2-)
DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)

kubectl -n staging create secret generic hkhr-secrets --from-literal=REDIS_URL="$REDIS_URL" --from-literal=DATABASE_URL="$DATABASE_URL"

unset REDIS_URL DATABASE_URL
```

For staging, `DATABASE_URL` must be the **staging** branch's URL.

### Deploy and use

```bash
kubectl apply -k k8s/overlays/staging
kubectl get pods -n staging -w                 # wait for 1/1 Running
kubectl logs deploy/order-service -n staging --tail=5

kubectl port-forward -n staging svc/frontend 5000:5000 > /tmp/pf-frontend.log 2>&1 &
kubectl port-forward -n staging svc/order-service 5001:5001 > /tmp/pf-order.log 2>&1 &
pkill -f "kubectl port-forward"                # when you are done
```

A port-forward is tied to one pod, so start it again after any `rollout restart`.

## 6. Production deployment

Production runs in the `production` namespace on the same kind cluster, with its own Neon
branch, its own Secret and ConfigMap, and its own stream prefix.

### 1. Neon production branch

1. Neon console, project `hkhr-store-saga-db`, **Branches**, **Create branch**.
2. Name `production`, parent `dev`, data option **Branch schema only**, **Auto-delete: Never**.
3. Check: the Branches page shows a Schema-only badge, and **Tables** (database `neondb`) lists
   `orders`, `payments`, `reservations`, `stock` with 0 rows. The empty `hkhr_prod`
   database is not used.

### 2. Create the Secret

Hidden prompts keep the values out of the terminal and shell history. Paste each value once
and press Enter:

```bash
read -rsp "Production Neon URL: " PROD_DB; echo
read -rsp "Upstash REDIS_URL: " REDIS; echo
echo "db length: ${#PROD_DB}  redis length: ${#REDIS}"      # sanity check, not the values
kubectl create secret generic hkhr-secrets -n production \
  --from-literal=DATABASE_URL="$PROD_DB" --from-literal=REDIS_URL="$REDIS"
unset PROD_DB REDIS
```

Check the secret without printing it:

```bash
kubectl -n production describe secret hkhr-secrets            # key names and sizes
kubectl -n production get secret hkhr-secrets -o jsonpath='{.data.REDIS_URL}' | base64 -d | grep -o '://' | wc -l   # must print 1
```

`hkhr-config` comes from the production overlay. To change `ORDER_API_URL`, `ALLOWED_ORIGINS` or
`WAKE_URLS`, edit the `configMapGenerator` literals in `k8s/overlays/production/kustomization.yaml`
and redeploy.

### 3. Deploy

```bash
kubectl kustomize k8s/overlays/production | kubectl apply -f -
kubectl -n production get pods -w                  # wait for five pods 1/1 Running
kubectl -n production logs deploy/order-service --tail=20
```

The Jenkins `main` pipeline runs the same command after a manual approval (see below).

### 4. Test

```bash
kubectl -n production port-forward svc/frontend 5000:5000          # terminal 1
kubectl -n production port-forward svc/order-service 5001:5001     # terminal 2
curl -s <order-service address>/health                             # prints: ok
```

In Codespaces, open port 5000 from the **Ports** tab (globe icon) and set 5001 to **Public**
while testing. The production `stock` table is empty (schema-only branch), so insert stock
rows in the Neon SQL Editor (branch `production`, database `neondb`) before testing the happy
path. Then run the orders in [Things to try](#things-to-try).

## 7. CI/CD

- **GitHub Actions** (`.github/workflows/cicd.yml`, "CI/CD Pipeline") runs lint and tests on
  pushes and pull requests.
- **Branches:** work on `dev`, open a pull request into `main` once CI is green.
- **Jenkins** runs in a Docker container (image from `jenkins/Dockerfile` with the Docker CLI
  and kubectl) as a multibranch job, `hkhr-store-saga`, reading the `Jenkinsfile`:

| Stage | Runs on |
|---|---|
| Prepare, Test (mock tests) | every branch |
| Build images, Push images (tagged with the commit, to GHCR) | `dev`, `main` |
| Deploy to staging | `dev` |
| Approve production (manual input) | `main` |
| Deploy to production | `main` |

The deploy stages run
`kubectl kustomize k8s/overlays/<env> | sed "s#:dev#:$TAG#" | kubectl apply -f -`
and then wait for each deployment's rollout. Jenkins needs a kubeconfig for the kind cluster:
**rebuild the cluster, and you must give Jenkins a new kubeconfig.** The Secret
for the target namespace must exist before the first deploy.

## 8. Deploy on Render (optional, not deployed yet)

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
| `password authentication failed` after resetting a password | An old `DATABASE_URL` is exported in the shell, or the secret still has the old password | `unset` the variables, `docker compose down`, then `up --build`; recreate the Secret and `rollout restart` |
| Page loads but placing an order fails in the browser ("Could not reach the order service") | `ORDER_API_URL` or `ALLOWED_ORIGINS` wrong or missing in `hkhr-config`, port 5001 private, or the port-forward died | Use the forwarded addresses, no trailing slash, set 5001 Public, restart the forward |
| `docker login` says `denied` | Token empty, too long (extra text pasted) or missing `write:packages` | Re-enter the token, check its length is 40 |
| `not found` pulling an image from GHCR | Tag not pushed, or package private | Push again and set the package to Public |
| `kubectl` says `connection refused` to `127.0.0.1:<port>` | The kind container is stopped | `docker start hkhr-control-plane`, or rebuild the cluster |
| `docker start` fails with `RWLayer ... is unexpectedly nil` | Damaged kind container | `kind delete cluster --name hkhr`, `docker rm -f hkhr-control-plane`, `kind create cluster --name hkhr`, then recreate namespaces, Secrets, ConfigMaps and Jenkins' kubeconfig |
| `kubectl` returns an HTML "Authentication required" page | No cluster in kubeconfig, so `kubectl` fell back to `localhost:8080`, which is Jenkins | Create the cluster |
| `kubectl` says `localhost:8080 refused` | No cluster exists | `kind create cluster --name hkhr` |
| Pod `CreateContainerConfigError`, `secret "hkhr-secrets" not found` | The Secret is created by hand and does not exist in that namespace | Create it, then `rollout restart`. List what is missing with `kubectl -n <ns> get events --sort-by=.lastTimestamp \| grep -i "not found"` |
| Pod `CreateContainerConfigError`, `configmap "hkhr-config" not found` | The overlay has no `configMapGenerator` block, or the overlay file is broken | Check that `kubectl kustomize k8s/overlays/<env>` renders the ConfigMap and the Deployments, then redeploy |
| Workers crash with `Port could not be cast to integer value ... 'rediss:'` | `REDIS_URL` was pasted twice into the Secret | Delete and recreate the Secret; the `://` count check must print 1 |
| Pod stuck in `ImagePullBackOff` | Image missing or private | Check the image name and that the package is Public |
| Order fails with `database unavailable` or `event broker unavailable` | `DATABASE_URL` or `REDIS_URL` wrong in the Secret | Recreate the Secret, `rollout restart deployment` |

## What I learned operating this

**A deploy that failed with healthy images.** A Jenkins `dev` build failed in **Deploy to staging**
after Test, Build and Push had passed. The log ended with
`error: timed out waiting for the condition` while waiting for the frontend rollout.

- **Finding it:** the pods were in `CreateContainerConfigError`. `kubectl get events` filtered
  for `not found` named the missing objects: the ConfigMap `hkhr-config` and the Secret
  `hkhr-secrets`. Both had been created by hand in the `production` namespace and never in `staging`.
- **Fixing it:** I created the Secret in staging and moved the ConfigMap into both overlays with
  `configMapGenerator`, so it is now part of every deploy. The Secret stays out of git.
- **Checking it:** `kubectl kustomize k8s/overlays/<env>` shows what will be applied, and
  `kubectl diff` showed no change to the live production objects before I pushed.

**A mistake I caught.** While editing the staging overlay I broke it: the file lost its
`resources:` and `patches:` and ended up with a duplicate `configMapGenerator:`. The render
showed only a ConfigMap and no Deployments. A pipeline can still go green in that state,
because the rollout wait passes against the old pods while nothing new is deployed. I restored
the file from git history and re-added the block once.

**Takeaways**

- Look at the rendered manifests before pushing, not only whether the build is green.
- Anything created by hand in one namespace is a gap in the others. Put what you can in git.
- Read the first error in a log, not the last lines. The end of a failed Jenkins run is only cleanup.
- A manual approval prompt is easy to miss. Here the button is labeled **Deploy**, and an
  unanswered prompt eventually ends as aborted.

## Security notes

- Never commit `.env`. It is in `.gitignore`; check `git status --short` before each commit
  (`git ls-files .env` should print nothing).
- Treat the Upstash password, the Neon password and GitHub tokens as secrets. If one appears in
  a screenshot, chat or log, reset it once the project holds real data.
- Keep Codespaces ports **Private** unless a browser must call them directly; set 5001 back
  to Private after testing.
- Mounting the Docker socket into Jenkins gives it full control of the host's Docker. Do this only
  in a throwaway development environment.

## Status

| Step | State |
|---|---|
| Saga services, unit and mock tests, GitHub Actions CI | Done |
| Dockerfiles and Docker Compose | Done |
| Images in GHCR, public | Done |
| kind cluster and base manifests | Done |
| Jenkins pipeline: test, build, push, deploy to staging | Done (builds `dev`, deploys to `staging`) |
| Separate Neon branches for dev, staging, production | Done |
| Staging overlay deployed and tested (happy path, payment failure, insufficient stock) | Done |
| Production overlay deployed and tested in the `production` namespace | Done (applied with `kubectl kustomize`) |
| Production deploy through the Jenkins main pipeline with approval | Done (approved in the Jenkins stage view, then verified in the production namespace) |
| Separate Redis for production | To do (free plan allows one database) |

## Known limitations

- **One shared Upstash Redis.** Production is separated only by the `prod:` prefix. A real
  system would use a separate broker. Dev and staging share unprefixed streams.
- **`hkhr-secrets` is created by hand.** `hkhr-config` is generated by each overlay (`configMapGenerator`), but the Secret holds credentials and stays out of Git. Rebuilding the cluster means recreating it.
- **`ORDER_API_URL` in the overlays contains the Codespace name.** If the Codespace is recreated, update it in both overlays.
- **The kind cluster lives in a Codespace.** Damage to the container (the `RWLayer` error) loses
  the cluster and everything in it, so keep the commands above to rebuild it.
- Manual deploys use the `:dev` image tag; the pipeline swaps in the commit tag.

## Concepts this project demonstrates

- **Database per service**: no service reads another service's tables.
- **Saga (choreography)**: a business transaction spread across services with no central coordinator.
- **Compensating transaction**: `PaymentFailed` makes inventory release the stock.
- **Idempotent consumers**: duplicate deliveries don't double-reserve or double-charge
  (unique `order_id` keys, status checks).
- **At-least-once delivery**: consumer groups + ack + retry after 30s + dead-letter stream.
- **Containers and orchestration**: one image per service, the same images run under Compose
  and Kubernetes, configuration injected through environment variables, Secrets and ConfigMaps.
- **Environment isolation**: Neon branches for data, Kubernetes namespaces for workloads,
  stream prefixes for events.
- **CI/CD**: GitHub Actions for checks, Jenkins for build, push and gated deploys.
- **Known limitation, the dual-write problem**: a service commits to its DB and then publishes.
  A crash in between is repaired by re-publishing on redelivery here, but production systems
  use the **transactional outbox pattern**. A good next exercise.
