from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

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


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
