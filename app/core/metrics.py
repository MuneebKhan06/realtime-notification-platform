from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

active_connections = Gauge(
    "notification_gateway_active_connections",
    "Number of live WebSocket connections held by this instance",
)

notifications_persisted_total = Counter(
    "notification_gateway_notifications_persisted_total",
    "Notifications written to PostgreSQL",
)

notifications_delivered_live_total = Counter(
    "notification_gateway_notifications_delivered_live_total",
    "Notifications published to a Redis Pub/Sub channel for live delivery",
)

ws_messages_received_total = Counter(
    "notification_gateway_ws_messages_received_total",
    "Inbound WebSocket messages received, by type",
    ["message_type"],
)

rate_limited_total = Counter(
    "notification_gateway_rate_limited_total",
    "Inbound WebSocket messages dropped by the rate limiter",
)

read_receipts_recorded_total = Counter(
    "notification_gateway_read_receipts_recorded_total",
    "Read receipts persisted for delivered notifications",
)

delivery_latency_seconds = Histogram(
    "notification_gateway_delivery_latency_seconds",
    "Time from a notification being published to Redis Pub/Sub to being"
    " pushed down the recipient's local WebSocket",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
