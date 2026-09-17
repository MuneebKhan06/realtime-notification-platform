import logging

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.middleware import (
    REQUEST_ID_HEADER,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)


def make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {"pong": True}

    return app


def make_app_with_security_headers() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {"pong": True}

    return app


def test_response_carries_a_request_id_header():
    client = TestClient(make_app())

    response = client.get("/ping")

    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert len(response.headers[REQUEST_ID_HEADER]) > 0


def test_incoming_request_id_is_echoed_back():
    client = TestClient(make_app())

    response = client.get("/ping", headers={REQUEST_ID_HEADER: "caller-supplied-id"})

    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"


def test_request_is_logged_with_structured_fields(caplog):
    client = TestClient(make_app())

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/ping", headers={REQUEST_ID_HEADER: "caller-supplied-id"})

    # Filtered rather than asserting on the total record count: importing
    # app.main elsewhere in the suite configures the root logger as a side
    # effect, which can let unrelated INFO logs (e.g. httpx's own request
    # log) reach caplog too.
    request_records = [r for r in caplog.records if r.name == "app.request"]
    assert len(request_records) == 1
    record = request_records[0]
    assert record.request_id == "caller-supplied-id"
    assert record.method == "GET"
    assert record.path == "/ping"
    assert record.status_code == 200
    assert record.duration_ms >= 0


def test_security_headers_are_present_on_every_response():
    client = TestClient(make_app_with_security_headers())

    response = client.get("/ping")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "geolocation=()" in response.headers["Permissions-Policy"]


def test_security_headers_do_not_include_hsts():
    client = TestClient(make_app_with_security_headers())

    response = client.get("/ping")

    assert "Strict-Transport-Security" not in response.headers
