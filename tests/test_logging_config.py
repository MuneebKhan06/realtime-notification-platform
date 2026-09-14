import json
import logging
import sys

from app.core.logging_config import JsonFormatter


def _make_record(msg: str, level: int = logging.INFO, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_core_fields_as_json():
    formatter = JsonFormatter(instance_id="instance-1")
    record = _make_record("connection accepted")

    entry = json.loads(formatter.format(record))

    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["instance_id"] == "instance-1"
    assert entry["message"] == "connection accepted"
    assert "timestamp" in entry


def test_includes_extra_fields():
    formatter = JsonFormatter(instance_id="instance-1")
    record = _make_record("heartbeat received", user_id="user-42")

    entry = json.loads(formatter.format(record))

    assert entry["user_id"] == "user-42"


def test_includes_exception_details():
    formatter = JsonFormatter(instance_id="instance-1")
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record("handler failed")
        record.exc_info = sys.exc_info()

    entry = json.loads(formatter.format(record))

    assert "ValueError: boom" in entry["exception"]
