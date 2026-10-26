"""Shared formats, validation and structured errors."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
SCHEMA = 1
STATUSES = ("todo", "in_progress", "blocked", "awaiting_review", "done", "cancelled")
EVENT_TYPES = ("progress", "result", "blocker", "suggestion", "correction", "handoff", "acceptance")


class RelayError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


def fail(code, message, **details):
    raise RelayError(code, message, **details)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def uid():
    return str(uuid.uuid4())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(command, payload):
    return hashlib.sha256(canonical([command, {k: v for k, v in payload.items() if k != "request_id"}]).encode()).hexdigest()


def require(data, key, kind=str):
    value = data.get(key)
    if not isinstance(value, kind) or isinstance(value, bool) or (kind is str and not value.strip()):
        fail("invalid_input", f"{key} must be a non-empty {kind.__name__}")
    return value


def fields(data, allowed, required=()):
    if not isinstance(data, dict):
        fail("invalid_input", "Input must be a JSON object")
    unknown = set(data) - set(allowed) - {"request_id"}
    if unknown:
        fail("invalid_input", "Unknown input fields", fields=sorted(unknown))
    require(data, "request_id")
    for k in required:
        require(data, k)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        fail("integrity_error", "Cannot read JSON file", path=str(path), reason=str(exc))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
