"""Sessions, claims, fencing and explicit acceptance."""
from common import STATUSES, canonical, fail, fields, now, require, uid

OWNER_FIELDS = ("title", "objective", "acceptance_criteria", "current_summary", "next_step", "blocker", "status")


def session(store, data):
    sid = require(data, "session_id")
    s = store.get("sessions", "session_id", sid)
    if not s["active"] or s["instance_id"] != store.local["instance_id"]:
        fail("stale_claim", "Session belongs to an inactive or different local instance")
    return s


def owner(store, data):
    s = session(store, data)
    gen = require(data, "generation", int)
    claim = store.db.execute("SELECT * FROM claims WHERE task_id=?", (require(data, "task_id"),)).fetchone()
    if not claim or claim["session_id"] != s["session_id"] or claim["generation"] != gen:
        fail("stale_claim", "Read and acquire the current claim", current_claim=dict(claim) if claim else None)
    return s


def revision(store, data):
    task = store.get("tasks", "task_id", require(data, "task_id"))
    if task["revision"] != require(data, "expected_revision", int):
        fail("revision_conflict", "Read current task before updating", current_revision=task["revision"])
    return task


def update_task(store, data):
    owner(store, data)
    task = revision(store, data)
    if task["status"] in ("done", "cancelled"):
        fail("invalid_input", "Terminal task cannot be modified")
    changes = {k: data[k] for k in OWNER_FIELDS if k in data}
    if not changes or any(not isinstance(v, str) for v in changes.values()):
        fail("invalid_input", "Supply text task fields")
    if "status" in changes and changes["status"] not in STATUSES[:-2] + ("cancelled",):
        fail("invalid_input", "done requires explicit task accept")
    store.db.execute("UPDATE tasks SET " + ",".join(f"{k}=?" for k in changes)
                     + ",revision=revision+1,updated_at=? WHERE task_id=? AND revision=?",
                     (*changes.values(), now(), task["task_id"], task["revision"]))
    store.db.execute("UPDATE claims SET updated_at=? WHERE task_id=?", (now(), task["task_id"]))
    store.db.execute("UPDATE sessions SET last_activity=? WHERE session_id=?", (now(), data["session_id"]))
    if changes.get("status") == "cancelled":
        store.db.execute("UPDATE claims SET session_id=NULL,generation=generation+1 WHERE task_id=?", (task["task_id"],))
    return {"task_id": task["task_id"], "revision": task["revision"] + 1}


def action_for(store, command, data):
    from service import add_event
    if command == "session start":
        fields(data, ("environment",))
        if "environment" in data:
            require(data, "environment")

        def action():
            sid, t = uid(), now()
            store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,1)",
                             (sid, store.local["instance_id"], data.get("environment", store.local["environment"]), t, t))
            return {"session_id": sid}
    elif command == "task update":
        fields(data, (*OWNER_FIELDS, "task_id", "session_id", "generation", "expected_revision"),
               ("task_id", "session_id"))

        def action():
            return update_task(store, data)
    elif command in ("claim", "release", "recover"):
        fields(data, ("task_id", "session_id", "generation", "reason"), ("task_id", "session_id"))
        if command == "recover":
            require(data, "reason")

        def action():
            s = session(store, data)
            task = store.get("tasks", "task_id", data["task_id"])
            if task["status"] in ("done", "cancelled"):
                fail("invalid_input", "Cannot claim or recover a terminal task")
            row = store.db.execute("SELECT * FROM claims WHERE task_id=?", (data["task_id"],)).fetchone()
            c = dict(row) if row else None
            generation = c["generation"] if c else 0
            if command == "claim" and c and c["session_id"]:
                fail("claim_conflict", "Task is already held", current_claim=c,
                     holder=store.get("sessions", "session_id", c["session_id"]))
            if command == "release":
                owner(store, data)
                sid = None
            else:
                sid = s["session_id"]
            generation += 1
            store.db.execute("INSERT INTO claims VALUES (?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET "
                             "session_id=excluded.session_id,generation=excluded.generation,updated_at=excluded.updated_at",
                             (data["task_id"], sid, generation, now()))
            store.db.execute("UPDATE sessions SET last_activity=? WHERE session_id=?", (now(), s["session_id"]))
            content = canonical({"operation": command, "reason": data.get("reason", ""), "previous_claim": c,
                                 "session_id": sid, "generation": generation})
            eid = add_event(store, data, event_type="handoff", content=content)
            return {"task_id": task["task_id"], "revision": task["revision"], "session_id": sid,
                    "generation": generation, "event_id": eid}
    elif command == "task accept":
        fields(data, ("task_id", "session_id", "expected_revision", "confirmation_source", "note"),
               ("task_id", "session_id", "confirmation_source", "note"))

        def action():
            session(store, data)
            task = revision(store, data)
            if task["status"] != "awaiting_review":
                fail("invalid_input", "Only awaiting_review can be accepted")
            store.db.execute("UPDATE tasks SET status='done',revision=revision+1,updated_at=? WHERE task_id=?",
                             (now(), task["task_id"]))
            store.db.execute("UPDATE claims SET session_id=NULL,generation=generation+1,updated_at=? WHERE task_id=?",
                             (now(), task["task_id"]))
            eid = add_event(store, data, event_type="acceptance",
                            content=canonical({"confirmation_source": data["confirmation_source"], "note": data["note"]}))
            return {"task_id": task["task_id"], "event_id": eid, "revision": task["revision"] + 1}
    else:
        return None
    return action
