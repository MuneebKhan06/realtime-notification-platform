# Real-Time Notification & Presence Platform

A production-grade real-time backend built on WebSockets. Handles live
notifications, online/offline presence, and guaranteed delivery across
horizontally scaled server instances. This is the architecture pattern behind
Slack, Discord, and GitHub notifications, built from scratch to understand
what happens when a WebSocket connection needs to survive server restarts,
reconnects, and messages sent from a completely different server instance.

> **Domain:** Real-time systems, distributed backend architecture
> **Stack:** FastAPI, WebSockets, Redis (Pub/Sub + state), PostgreSQL, Docker Compose
> **Focus:** Backend and distributed systems

## Table of Contents

- [System Overview](#system-overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Architecture & Design Decisions](#architecture--design-decisions)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Development](#development)
- [Load Test Results](#load-test-results)
- [How I Would Scale This](#how-i-would-scale-this)
- [What I Would Do Differently](#what-i-would-do-differently)

---

## System Overview

```
Client A (WebSocket)                    Client B (WebSocket)
        |                                        |
        v                                        v
Gateway Instance 1                      Gateway Instance 2
   |                                        |
   | on connect:                            | on connect:
   | - validate ticket                      | - validate ticket
   | - register in Redis:                   | - register in Redis:
   |   user:A -> instance-1                  |   user:B -> instance-2
   | - replay missed notifications           | - replay missed notifications
   |   from PostgreSQL                       |   from PostgreSQL
   |                                         |
   +---------------------+-------------------+
                          |
                          v
              Redis Pub/Sub (fan-out channel)
                          |
        Every gateway instance subscribes to its own channel
                          |
   When the API publishes "notify user B":
   1. Look up user:B -> instance-2 in Redis
   2. Publish to channel: instance-2.deliver
   3. Instance-2 receives it, has the live
      WebSocket for B, pushes the message
                          |
                          v
                    PostgreSQL
        (every notification persisted here
         regardless of delivery outcome,
         the source of truth for history and replay)
```

---

## Architecture

### Components

| Component | Role |
|---|---|
| FastAPI (WebSocket) | Connection handling, ticket handshake auth, message routing |
| Redis Pub/Sub | Cross-instance message fan-out |
| Redis (connection registry) | Maps user_id to gateway instance_id, with TTL heartbeat |
| Redis (presence) | Online/away/offline state with TTL-based expiry |
| PostgreSQL | Notification persistence, delivery status, read receipts |
| Notification API | REST endpoint other services call to trigger a notification |
| Heartbeat and reconciliation | Refreshes liveness, detects and cleans up stale registry entries |
| Locust | Load testing concurrent connections and message throughput |

---

## Project Structure

```
realtime-notification-platform/
|
|-- .github/workflows/ci.yml         # Lint + tests on Python 3.10 and 3.11
|
|-- app/
|   |-- main.py                      # FastAPI app entry point and lifespan wiring
|   |-- config.py                    # pydantic-settings config
|   |
|   |-- websocket/
|   |   |-- connection_manager.py    # Tracks live connections on this instance
|   |   |-- gateway.py               # WebSocket endpoint: connect, receive, disconnect
|   |   |-- auth_handshake.py        # Single-use ticket exchange for the WS upgrade
|   |   |-- heartbeat.py             # Heartbeat handling and reconciliation loop
|   |   |-- message_router.py        # Routes incoming client messages by type
|   |
|   |-- pubsub/
|   |   |-- publisher.py             # Publish to Redis Pub/Sub channels
|   |   |-- subscriber.py            # Per-instance subscriber loop
|   |   |-- instance_registry.py     # user_id -> instance_id mapping in Redis
|   |
|   |-- presence/
|   |   |-- presence_manager.py      # Online/away/offline state machine
|   |   |-- presence_store.py        # Redis TTL-based presence storage
|   |
|   |-- api/routes/
|   |   |-- auth.py                  # POST /auth/ws-ticket
|   |   |-- notifications.py         # POST /notifications
|   |   |-- presence.py              # GET /presence/{user_id}
|   |   |-- history.py               # GET /notifications/history
|   |   |-- health.py
|   |   |-- metrics.py
|   |
|   |-- schemas/
|   |   |-- notifications.py         # Pydantic models for notification payloads
|   |   |-- ws_messages.py           # Client <-> server message envelope schemas
|   |
|   |-- db/
|   |   |-- connection.py
|   |   |-- models.py                # Notification, DeliveryLog, ReadReceipt models
|   |   |-- repository.py
|   |
|   |-- core/
|       |-- rate_limiter.py          # Per-connection message rate limiting
|       |-- idempotency.py           # Fast dedup check ahead of the DB write
|       |-- metrics.py               # Prometheus counters and gauges
|
|-- alembic/versions/                # 0001 notifications, 0002 delivery_log, 0003 read_receipts
|
|-- tests/                           # Unit tests (fakeredis) + marked integration test
|-- load_tests/                      # Locust WS load test + fan-out latency benchmark
|-- scripts/                         # ws_client_demo.py, simulate_notifications.py
|
|-- docker/Dockerfile.gateway        # Gateway image, stateless, horizontally scaled
|-- docker-compose.yml               # 3 gateway instances + Redis + PostgreSQL + Nginx (LB)
|-- docker-compose.test.yml          # 2 gateway instances for the integration test
|-- nginx/nginx.conf                 # Load balancer config, no sticky sessions, by design
|
|-- .env.example
|-- alembic.ini
|-- pyproject.toml
|-- pytest.ini
|-- requirements.txt
|-- requirements-dev.txt
|-- README.md
```

---

## Architecture & Design Decisions

### Decision 1: WebSockets over Server-Sent Events or long polling

Short polling wastes requests and adds latency up to the poll interval,
which is wrong for anything calling itself real-time. Long polling improves
latency but each held-open request still consumes a server connection slot
and requires re-establishing the connection after every response.

SSE is a strong option for notifications alone since delivery is
one-directional. It was rejected here specifically because presence needs
the client to send data back too: heartbeat pings and presence status
changes. SSE cannot carry that traffic, a second HTTP channel would be
needed for the reverse direction, which is more complexity than one
WebSocket connection.

**Tradeoffs accepted:** WebSocket connections are stateful, unlike stateless
HTTP requests, which is the source of nearly every other decision below.
Harder to load balance than HTTP (addressed in Decision 3). No automatic
browser reconnect (must be implemented client-side).

### Decision 2: Redis Pub/Sub vs Redis Streams for fan-out

A live notification fan-out message only matters if a recipient is
currently connected to receive it in real time. If no gateway instance is
subscribed and listening, there is nothing to persist and replay through
Pub/Sub, the client was not there to see it live regardless. The actual
durability requirement, surviving in PostgreSQL so a client can fetch
missed notifications on reconnect, is solved separately (Decision 6).

Pub/Sub's fire-and-forget nature is exactly right for "deliver to
instance-2 right now if it is listening." Redis Streams would add consumer
group bookkeeping for messages only ever meant to be delivered live, once,
to whichever instance currently holds the connection.

**Tradeoffs accepted:** If the target gateway instance crashes between
publish and delivery, the message is lost from Pub/Sub (mitigated: it is
already in PostgreSQL). No ordering guarantee across different channels.

### Decision 3: Horizontal scaling, the cross-instance delivery problem

With three gateway instances behind a load balancer, user A might be
connected to instance-1 and user B to instance-2. Instance-1 has no direct
connection to B's socket when A sends something that must reach B.

The chosen design is an instance registry in Redis (`user_id -> instance_id`)
with targeted per-instance Pub/Sub channels. On connect, each instance
writes `user:{user_id} -> instance:{instance_id}` into Redis with a TTL
refreshed by the heartbeat. Each instance subscribes only to its own
channel: `channel:instance-{instance_id}`. To notify user B, the API looks
up `user:B`, publishes to that one channel, and only that instance receives
it. This means load balancing does not need sticky sessions, Nginx here
uses plain round-robin.

**What happens if the user is not connected anywhere:** the Redis lookup
returns nothing, the publish is skipped, and delivery relies solely on the
PostgreSQL backlog fetched on the client's next connect.

**Tradeoffs accepted:** one extra Redis round trip per notification.
Registry entries must be cleaned up on disconnect and expire via TTL if the
disconnect was not graceful. A brief window during instance failover where
the registry is stale.

### Decision 4: Authentication during the WebSocket handshake

Browser WebSocket APIs cannot set custom headers on the initial handshake,
so a standard `Authorization: Bearer` header is awkward here. Putting the
JWT in the query string is a real security risk since query parameters are
logged by default in most reverse proxies and load balancers. Sending the
token as the first message avoids logging but leaves a window where an
unauthenticated connection can be held open indefinitely.

The chosen design is a single-use ticket exchange. The client calls
`POST /auth/ws-ticket` over regular HTTPS with its normal Bearer token. The
server generates a random one-time ticket, stores it in Redis with a
10-second TTL and the associated user_id, and returns it. The client opens
the WebSocket with `wss://host/ws?ticket={ticket}`. The ticket is deleted
from Redis the instant it is used (atomic get-and-delete), so it cannot be
replayed even if it leaks into a log.

**Tradeoffs accepted:** one extra HTTP round trip before the WebSocket can
open. Requires Redis availability before the WebSocket layer is reached.
Reconnect logic must request a new ticket each time.

### Decision 5: Presence and heartbeat design

Presence uses TTL-based state in Redis, refreshed by a client-driven
heartbeat rather than a server-driven ping to every connection at scale.

```
On connect:
  SET presence:{user_id} "online" EX 30

Client sends a heartbeat message every 15 seconds:
  SET presence:{user_id} "online" EX 30   (refresh the TTL)

If no heartbeat arrives within 30 seconds:
  Redis key expires naturally, presence considered offline
```

A naive design has the server ping every connected client, which means
O(connections) continuous server-side work. The TTL approach inverts this:
the client proves it is alive by refreshing its own key, and Redis expiry
does the offline detection for free with zero ongoing polling cost.

**Three presence states, not two:** `online` (heartbeat within the last 30
seconds), `away` (client explicitly reported backgrounded, still
connected), `offline` (key expired or connection closed). `away` is layered
on top of the same TTL mechanism, not a separate liveness signal.

**Tradeoffs accepted:** offline detection has up to 30 seconds of lag, a
deliberate tradeoff between detection speed and heartbeat traffic volume. A
periodic reconciliation loop double-checks registry entries against active
connections as a safety net against missed Redis keyspace notifications.

### Decision 6: Missed notification delivery and idempotency

Every notification is written to PostgreSQL first, before any Pub/Sub
publish is attempted. Pub/Sub delivery is best-effort and only matters for
the live case, PostgreSQL is the source of truth for what a user has and
has not seen.

```sql
CREATE TABLE notifications (
    id              BIGSERIAL PRIMARY KEY,
    notification_id UUID        NOT NULL UNIQUE,
    user_id         UUID        NOT NULL,
    type            VARCHAR(50) NOT NULL,
    payload         JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_live  BOOLEAN     NOT NULL DEFAULT FALSE,
    read_at         TIMESTAMPTZ
);
```

On connect, after the instance registers itself and before accepting live
traffic, the gateway queries unread notifications and pushes them down the
newly opened socket as a `backlog` message batch, distinct from live
`notification` messages.

**Idempotency:** `notification_id` is a caller-generated UUID. If the same
notification is submitted twice, a retry from a flaky upstream service, the
unique constraint on `notification_id` makes the second insert a no-op via
`ON CONFLICT DO NOTHING`. A Redis-backed idempotency guard sits ahead of the
database write as a fast, non-authoritative pre-check for the common case of
a retry arriving within a short window.

**Tradeoffs accepted:** backlog delivery adds one query to the connect
path. The backlog fetch is capped, a user offline for a long time with
heavy notification volume needs pagination via the history endpoint.
`delivered_live` is a best-effort flag, it records whether a live publish
was attempted, not whether the client's UI actually rendered it.

### Decision 7: Per-connection rate limiting and backpressure

A misbehaving client could flood the WebSocket with messages, consuming
server resources. This is bounded with a token bucket per connection,
evaluated atomically via a Redis Lua script so concurrent messages on the
same connection cannot race past the limit between a read and a write. A
client exceeding the configured limit has individual messages dropped with
a `rate_limited` error frame, the connection itself is never closed for
this, closing on a rate limit is a harsh response to what is often just an
aggressive but legitimate client.

**Tradeoffs accepted:** dropped messages are not queued for later, a
rate-limited client loses those specific messages rather than experiencing
delay.

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.10+

### 1. Clone the repository

```
git clone https://github.com/MuneebKhan06/realtime-notification-platform.git
cd realtime-notification-platform
```

### 2. Set up environment variables

```
cp .env.example .env
```

### 3. Start the full stack

```
docker-compose up -d
```

This starts three gateway instances (demonstrating horizontal scaling),
Redis, PostgreSQL, and Nginx as a plain round-robin load balancer (no
sticky sessions, by design, see Decision 3).

### 4. Verify everything is running

```
docker-compose ps
curl http://localhost:8000/health
```

### 5. Get a WebSocket ticket and connect

```
curl -X POST http://localhost:8000/auth/ws-ticket \
  -H "Authorization: Bearer YOUR_JWT"

python scripts/ws_client_demo.py --ticket YOUR_TICKET
```

### 6. Trigger a notification from another terminal

```
curl -X POST http://localhost:8000/notifications \
  -H "Content-Type: application/json" \
  -d '{
    "notification_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "user-123",
    "type": "message.received",
    "payload": {"from": "Ayesha", "preview": "Are we still on for tomorrow?"}
  }'
```

### 7. Prove cross-instance delivery

```
python scripts/ws_client_demo.py --ticket TICKET_A   # lands on instance-1
python scripts/ws_client_demo.py --ticket TICKET_B   # lands on instance-2
# trigger a notification for B's user_id, watch it arrive on the instance-2 client
```

### 8. Run tests

```
pip install -r requirements-dev.txt
pytest tests/ -v -m "not integration"
```

### 9. Run load tests

```
locust -f load_tests/ws_locustfile.py --host=ws://localhost:8000
```

---

## API Reference

### POST /auth/ws-ticket

Exchange a Bearer JWT for a single-use WebSocket connection ticket (10s TTL).

```json
{"ticket": "a1b2c3...", "expires_in": 10}
```

### WS /ws?ticket={ticket}

Upgrade to a WebSocket connection. On success, immediately receives:

```json
{"type": "backlog", "notifications": [ ... up to 100 unread ... ]}
```

**Client -> server message types:** `heartbeat`, `presence_update`, `read_receipt`

**Server -> client message types:** `notification`, `backlog`, `rate_limited`, `error`

### POST /notifications

Trigger a notification for a user (called by other backend services).

```json
{
  "notification_id": "uuid",
  "user_id": "uuid",
  "type": "message.received",
  "payload": {}
}
```

### GET /notifications/history

Paginated notification history for a user.

**Query parameters:** `user_id`, `limit` (default 50), `before` (cursor, timestamp)

```json
{
  "notifications": [ { "notification_id": "uuid", "type": "message.received", "...": "..." } ],
  "next_cursor": "2026-01-01T00:00:00Z"
}
```

`next_cursor` is `null` once fewer than `limit` rows come back. Pass it as
the next request's `before` to page further into the history.

### GET /presence/{user_id}

```json
{"user_id": "uuid", "status": "online", "last_seen": "2026-01-01T00:00:00Z"}
```

### GET /health

```json
{
  "status": "healthy",
  "instance_id": "instance-2",
  "redis": "connected",
  "database": "connected",
  "active_connections": 412
}
```

### GET /metrics

Prometheus exposition format.

---

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
make check   # lint, type check, unit tests
```

`make check` runs ruff, mypy, and the unit test suite together, the same
checks CI runs. See the Makefile for individual targets (`lint`,
`typecheck`, `test-unit`, `test-integration`, `up`, `down`, `migrate`).

Optionally install the pre-commit hooks so lint and formatting run before
each commit:

```bash
pre-commit install
```

### Integration tests (two-instance delivery)

```bash
docker-compose -f docker-compose.test.yml up -d --build
pytest tests/test_integration.py -m integration
docker-compose -f docker-compose.test.yml down -v
```

---

## Load Test Results

> Tested on: [your machine specs]
> 3 gateway instances behind Nginx round-robin, Docker Compose, single host.

### Concurrent connection capacity

| Concurrent Connections | Memory per instance | CPU per instance | Connection success rate |
|---|---|---|---|
| 1,000 | TBD | TBD | TBD |
| 5,000 | TBD | TBD | TBD |
| 10,000 | TBD | TBD | TBD |

### Cross-instance delivery latency

| Scenario | P50 latency | P95 latency | P99 latency |
|---|---|---|---|
| Same-instance delivery | TBD | TBD | TBD |
| Cross-instance delivery (via Redis Pub/Sub) | TBD | TBD | TBD |

### Notification throughput

| Notifications/sec triggered | Delivered live (%) | Avg delivery latency |
|---|---|---|
| 100 | TBD | TBD |
| 1,000 | TBD | TBD |

*Results to be filled in after a dedicated load testing pass with
`load_tests/ws_locustfile.py` and `load_tests/fanout_benchmark.py`.*

---

## How I Would Scale This

**Current:** 3 gateway instances, single Redis node, single PostgreSQL
node, tested on one host via Docker Compose.

**To 10x concurrent connections:**

- Scale gateway instances horizontally behind the load balancer, the
  architecture already supports this with no code change since the
  instance registry design (Decision 3) is what makes horizontal scaling
  correct in the first place
- Redis becomes the shared bottleneck at this point: move to Redis Cluster
  for the instance registry and presence keys, sharded by user_id
- Nginx round-robin is sufficient at this scale, a dedicated L4 load
  balancer would only be needed for TLS termination at very high
  connection counts

**To 100x concurrent connections:**

- Separate Redis instances for Pub/Sub, instance registry, and presence,
  each has a different access pattern and contention profile
- PostgreSQL write load from notification persistence becomes the
  bottleneck, partition the notifications table by created_at (monthly)
  and consider write batching for high-volume notification sources
- Gateway instances would need to run behind a connection-aware load
  balancer or use QUIC/HTTP-3 to reduce per-connection overhead

**Identified bottleneck at scale:** the single Redis node used for both the
instance registry and Pub/Sub. At very high notification rates, every
notification requires one Redis GET (registry lookup) plus one Redis
PUBLISH. Splitting these onto separate Redis instances, and eventually
Redis Cluster with consistent hashing on user_id, is the natural next step.

---

## What I Would Do Differently

The instance registry currently has a failure mode I would address with
more time: if a gateway instance crashes ungracefully (not a clean
shutdown), its entries in the Redis registry are only cleaned up by TTL
expiry, which can leave a stale `user:X -> instance:crashed` mapping for up
to 30 seconds. During that window, notifications for user X are published
to a dead instance's channel and silently lost from the live path (though
still recoverable via PostgreSQL backlog on reconnect).

The correct fix is each gateway instance maintaining its own heartbeat key
(`instance:{id}:alive`, refreshed every few seconds) and the notification
publisher checking that key exists before trusting the registry entry,
falling back to "treat as offline, rely on backlog" if the owning instance
itself looks dead. I did not implement this because it adds a second TTL
check to every notification's hot path, and for this project's scope, the
30-second window of degraded (not lost) delivery was an acceptable
simplification to document rather than solve. In a production system
handling this at scale, I would implement the instance-liveness check from
day one.
