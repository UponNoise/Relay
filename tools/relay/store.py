"""SQLite ownership, project discovery and short write transactions."""
import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from common import SCHEMA, canonical, fail, fingerprint, now, read_json, require, uid, write_json

DDL = """
CREATE TABLE project (
 project_id TEXT PRIMARY KEY, name TEXT NOT NULL, goal TEXT NOT NULL, scope TEXT NOT NULL,
 working_agreements TEXT NOT NULL, acceptance_policy TEXT NOT NULL, schema_version INTEGER NOT NULL,
 revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE tasks (
 task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(project_id),
 title TEXT NOT NULL, objective TEXT NOT NULL, acceptance_criteria TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('todo','in_progress','blocked','awaiting_review','done','cancelled')),
 current_summary TEXT NOT NULL, next_step TEXT NOT NULL, blocker TEXT NOT NULL,
 revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE sessions (
 session_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, environment TEXT NOT NULL,
 created_at TEXT NOT NULL, last_activity TEXT NOT NULL, active INTEGER NOT NULL);
CREATE TABLE claims (
 task_id TEXT PRIMARY KEY REFERENCES tasks(task_id), session_id TEXT REFERENCES sessions(session_id),
 generation INTEGER NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE events (
 event_id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(task_id), event_type TEXT NOT NULL,
 content TEXT NOT NULL, source_environment TEXT NOT NULL, session_id TEXT,
 recorded_at TEXT NOT NULL, evidence_refs TEXT NOT NULL, request_id TEXT NOT NULL);
CREATE TABLE decisions (
 decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(project_id),
 task_id TEXT REFERENCES tasks(task_id), statement TEXT NOT NULL, rationale TEXT NOT NULL,
 provenance TEXT NOT NULL, confirmation_reference TEXT NOT NULL,
 supersedes TEXT REFERENCES decisions(decision_id), created_at TEXT NOT NULL);
CREATE TABLE evidence (
 evidence_id TEXT PRIMARY KEY, kind TEXT NOT NULL, locator TEXT NOT NULL, description TEXT NOT NULL,
 digest TEXT, verification_method TEXT, verified_at TEXT);
CREATE TABLE requests (
 request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
CREATE INDEX events_task_time ON events(task_id, recorded_at);
"""


def connect(path):
    db = sqlite3.connect(path, timeout=0.25, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=250")
    return db


def discover(explicit=None):
    if explicit:
        root = Path(explicit).resolve()
        if not (root / ".relay").is_dir():
            fail("not_found", "No Relay project at explicit path", path=str(root))
        return root
    cwd = Path.cwd().resolve()
    candidates = [p for p in (cwd, *cwd.parents) if (p / ".relay").is_dir()]
    if len(candidates) > 1:
        fail("project_mismatch", "Nested Relay projects; select --project explicitly")
    if not candidates:
        fail("not_found", "No Relay project found; use --project")
    return candidates[0]


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        meta = read_json(self.root / ".relay/project.json")
        self.local = read_json(self.root / ".relay/local.json")
        if not isinstance(meta, dict) or not isinstance(self.local, dict):
            fail("integrity_error", "Project metadata must be JSON objects")
        if meta.get("schema_version") != SCHEMA:
            fail("incompatible_version", "Only schema 1 is supported")
        path = self.root / ".relay/state.sqlite3"
        if not path.is_file():
            fail("integrity_error", "Database is missing")
        self.db = connect(path)
        try:
            p = self.project()
            if p["schema_version"] != SCHEMA:
                fail("incompatible_version", "Only schema 1 is supported")
            if p["project_id"] != meta.get("project_id"):
                fail("project_mismatch", "Database and project.json identities differ")
            require(self.local, "instance_id")
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def project(self):
        rows = self.db.execute("SELECT * FROM project").fetchall()
        if len(rows) != 1:
            fail("integrity_error", "Expected exactly one project")
        return dict(rows[0])

    def get(self, table, key, value):
        row = self.db.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        if row is None:
            fail("not_found", f"{table} record not found", id=value)
        return dict(row)

    def write(self, command, data, action):
        request_id = require(data, "request_id")
        digest = fingerprint(command, data)
        for attempt in range(4):
            try:
                self.db.execute("BEGIN IMMEDIATE")
                prior = self.db.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
                if prior:
                    if prior["fingerprint"] != digest:
                        fail("duplicate_request_mismatch", "Request ID already used for different input")
                    self.db.rollback()
                    return json.loads(prior["result"])
                result = action()
                self.db.execute("UPDATE project SET revision=revision+1, updated_at=?", (now(),))
                result.setdefault("revision", self.project()["revision"])
                result["project_revision"] = self.project()["revision"]
                result["request_id"] = request_id
                self.db.execute("INSERT INTO requests VALUES (?,?,?)", (request_id, digest, canonical(result)))
                self.db.commit()
                return result
            except sqlite3.OperationalError as exc:
                self.db.rollback()
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                if attempt == 3:
                    fail("database_busy", "Database busy after bounded retries")
                time.sleep(0.05 * (attempt + 1))
            except Exception:
                self.db.rollback()
                raise


def initialize(root, data):
    from common import fields
    fields(data, ("name", "goal", "scope", "working_agreements", "acceptance_policy", "environment"),
           ("name", "goal"))
    root = Path(root).resolve()
    state = root / ".relay"
    target_tool = root / "tools/relay"
    source = Path(__file__).parent.resolve()
    if state.exists():
        if (state / "state.sqlite3").is_file():
            old = Store(root)
            try:
                row = old.db.execute("SELECT * FROM requests WHERE request_id=?", (data["request_id"],)).fetchone()
                if row and row["fingerprint"] == fingerprint("init", data):
                    return json.loads(row["result"])
                if row:
                    fail("duplicate_request_mismatch", "init request changed")
            finally:
                old.close()
        fail("invalid_input", "Project already initialized; refusing to overwrite")
    if target_tool.exists() and target_tool.resolve() != source:
        fail("invalid_input", "tools/relay already exists; refusing to overwrite")
    for k in ("scope", "working_agreements", "acceptance_policy", "environment"):
        if k in data:
            require(data, k)
    root.mkdir(parents=True, exist_ok=True)
    project_id, instance_id, timestamp = uid(), uid(), now()
    result = {"project_id": project_id, "revision": 1, "request_id": data["request_id"], "instance_id": instance_id}
    with tempfile.TemporaryDirectory(prefix="relay-init-", dir=root) as tmp:
        temp = Path(tmp) / ".relay"
        temp.mkdir()
        db = connect(temp / "state.sqlite3")
        try:
            db.executescript(DDL)
            db.execute("INSERT INTO project VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (project_id, data["name"], data["goal"], data.get("scope", ""),
                        data.get("working_agreements", ""), data.get("acceptance_policy", "用户明确确认"),
                        SCHEMA, 1, timestamp, timestamp))
            db.execute("INSERT INTO requests VALUES (?,?,?)",
                       (data["request_id"], fingerprint("init", data), canonical(result)))
            db.execute("PRAGMA journal_mode=WAL")
        finally:
            db.close()
        write_json(temp / "project.json", {"project_id": project_id, "schema_version": SCHEMA})
        write_json(temp / "local.json", {"instance_id": instance_id, "environment": data.get("environment", "local"), "resources": {}})
        shutil.copyfile(source / "PROTOCOL.md", temp / "PROTOCOL.md")
        # Directory creation is exclusive; never replace an existing project.
        state.mkdir()
        for item in temp.iterdir():
            item.rename(state / item.name)
    if target_tool.resolve() != source:
        target_tool.parent.mkdir(exist_ok=True)
        shutil.copytree(source, target_tool, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "artifacts").mkdir(exist_ok=True)
    return result
