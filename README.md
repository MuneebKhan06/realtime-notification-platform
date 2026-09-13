# Real-Time Notification & Presence Platform

A production-grade real-time backend built on WebSockets. Handles live
notifications, online/offline presence, and guaranteed delivery across
horizontally scaled server instances.

Stack: FastAPI, WebSockets, Redis (Pub/Sub and state), PostgreSQL, Docker Compose.

This README will be filled in as the implementation lands. See the design
document for the full architecture, API reference, and decision log.

## Status

Work in progress. Project scaffolding, database schema, Redis coordination
layer, WebSocket gateway, and REST API are being built out incrementally.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
pytest tests/
ruff check app/ tests/
```
