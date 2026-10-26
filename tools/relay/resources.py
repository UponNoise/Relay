"""Portable evidence locators and local-only configuration."""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from common import canonical, fail, fields, fingerprint, now, read_json, require, uid, write_json


def relative_name(value):
    if not isinstance(value, str) or not value or "\\" in value:
        fail("invalid_input", "Use a non-empty forward-slash relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or PureWindowsPath(value).drive or any(x in ("", ".", "..") for x in value.split("/")) or ":" in value:
        fail("invalid_input", "Unsafe relative path", path=value)
    # Windows reserved names/aliases are not portable, even when imported on POSIX.
    for part in p.parts:
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            fail("invalid_input", "Non-portable path", path=value)
    return p


def inside(root, name):
    rel = relative_name(name)
    root = Path(root).resolve()
    path = root.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(root):
        fail("invalid_input", "Path escapes root", path=name)
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            fail("invalid_input", "Symbolic links and junctions are not supported", path=name)
    return path


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_path(root, local, evidence):
    locator = evidence["locator"]
    if evidence["kind"] == "project_file":
        return inside(root, locator)
    if evidence["kind"] == "external_file":
        if not locator.startswith("resource:") or "/" not in locator:
            fail("invalid_input", "External locator requires resource:name/path")
        name, tail = locator[9:].split("/", 1)
        relative_name(name)
        relative_name(tail)
        base = local.get("resources", {}).get(name)
        if not base:
            fail("missing_resource", "External resource is not mapped", resource=name)
        return inside(Path(base), tail)
    return None


def validate_evidence(store, data):
    fields(data, ("kind", "locator", "description", "digest", "verification_method", "verified_at"),
           ("kind", "locator", "description"))
    kind = data["kind"]
    if kind not in ("project_file", "external_file", "url", "note"):
        fail("invalid_input", "Unsupported evidence kind")
    if kind == "project_file":
        inside(store.root, data["locator"])
    elif kind == "external_file":
        loc = data["locator"]
        if not loc.startswith("resource:") or "/" not in loc[9:]:
            fail("invalid_input", "External locator requires resource:name/path")
        name, tail = loc[9:].split("/", 1)
        if "/" in name:
            fail("invalid_input", "Invalid resource name")
        relative_name(name)
        relative_name(tail)
    elif kind == "url":
        parsed = urlsplit(data["locator"])
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            fail("invalid_input", "URL must use http or https; Relay never downloads it")
    if "digest" in data:
        d = require(data, "digest")
        if len(d) != 64 or any(c not in "0123456789abcdef" for c in d):
            fail("invalid_input", "digest must be lowercase SHA256")
    for k in ("verification_method", "verified_at"):
        if k in data:
            require(data, k)


def check_evidence(store, evidence):
    result = {"evidence_id": evidence["evidence_id"], "kind": evidence["kind"], "locator": evidence["locator"]}
    try:
        path = evidence_path(store.root, store.local, evidence)
        if path is None:
            return {**result, "ok": True, "checked": False, "note": "Reference only; URL not fetched"}
        if not path.is_file():
            fail("missing_resource", "Referenced file is missing")
        digest = hash_file(path)
        if evidence.get("digest") and evidence["digest"] != digest:
            fail("integrity_error", "Evidence digest mismatch")
        return {**result, "ok": True, "checked": True, "sha256": digest}
    except Exception as exc:
        from common import RelayError
        if not isinstance(exc, (RelayError, OSError)):
            raise
        return {**result, "ok": False, "code": getattr(exc, "code", "missing_resource"), "message": str(exc)}


def set_local(store, data):
    """Local control-plane receipt lives only in local.json, never in portable DB."""
    fields(data, ("environment", "resources"))
    if "environment" in data:
        require(data, "environment")
    resources = data.get("resources")
    if resources is not None:
        if not isinstance(resources, dict):
            fail("invalid_input", "resources must map names to absolute roots")
        for key, value in resources.items():
            relative_name(key)
            if "/" in key or not isinstance(value, str) or not Path(value).is_absolute():
                fail("invalid_input", "Resource mapping must be name: absolute path")
    lock = store.root / ".relay/local.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        fail("database_busy", "Local configuration is being changed; retry later")
    try:
        handle.close()
        local = read_json(store.root / ".relay/local.json")
        receipts = local.setdefault("_requests", {})
        prior = receipts.get(data["request_id"])
        fp = fingerprint("local set", data)
        if prior:
            if prior["fingerprint"] != fp:
                fail("duplicate_request_mismatch", "Local request ID input differs")
            return prior["result"]
        for k in ("environment", "resources"):
            if k in data:
                local[k] = data[k]
        local["revision"] = local.get("revision", 0) + 1
        result = {"instance_id": local["instance_id"], "revision": local["revision"], "request_id": data["request_id"]}
        receipts[data["request_id"]] = {"fingerprint": fp, "result": result}
        tmp = store.root / ".relay" / ("local-" + uid() + ".tmp")
        try:
            write_json(tmp, local)
            tmp.replace(store.root / ".relay/local.json")
        finally:
            tmp.unlink(missing_ok=True)
        return result
    finally:
        lock.unlink(missing_ok=True)
