"""Business operations; all authoritative writes use Store.write."""
from common import EVENT_TYPES, fail, fields, now, require, uid, canonical


def add_event(store, data, event_type=None, content=None):
    from ownership import session
    source = session(store, data)
    task_id = data.get("task_id")
    if task_id:
        store.get("tasks", "task_id", task_id)
    refs = data.get("evidence_refs", [])
    if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
        fail("invalid_input", "evidence_refs must be an array of evidence IDs")
    for ref in refs:
        store.get("evidence", "evidence_id", ref)
    eid = uid()
    store.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                     (eid, task_id, event_type or data.get("event_type", "progress"),
                      content if content is not None else data["content"],
                      source["environment"], source["session_id"],
                      now(), canonical(refs), data["request_id"]))
    store.db.execute("UPDATE sessions SET last_activity=? WHERE session_id=?", (now(), source["session_id"]))
    return eid


def mutate(store, command, data):
    from ownership import OWNER_FIELDS, action_for, update_task
    action = action_for(store, command, data)
    if action:
        return store.write(command, data, action)
    if command == "task create":
        fields(data, ("title", "objective", "acceptance_criteria"), ("title", "objective", "acceptance_criteria"))

        def action():
            tid, t = uid(), now()
            store.db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (tid, store.project()["project_id"], data["title"], data["objective"],
                              data["acceptance_criteria"], "todo", "", "", "", 1, t, t))
            return {"task_id": tid, "revision": 1}
    elif command == "project update":
        allowed = ("name", "goal", "scope", "working_agreements", "acceptance_policy")
        fields(data, (*allowed, "expected_revision"))
        expected = require(data, "expected_revision", int)
        changes = {k: data[k] for k in allowed if k in data}
        if not changes or any(not isinstance(v, str) for v in changes.values()):
            fail("invalid_input", "Provide text project fields")

        def action():
            p = store.project()
            if p["revision"] != expected:
                fail("revision_conflict", "Read current project revision", current_revision=p["revision"])
            store.db.execute("UPDATE project SET " + ",".join(f"{k}=?" for k in changes), tuple(changes.values()))
            return {"project_id": p["project_id"], "revision": expected + 1}
    elif command == "progress":
        fields(data, ("task_id", "content", "event_type", "evidence_refs", "session_id",
                      "generation", "expected_revision", *OWNER_FIELDS), ("content", "session_id"))
        if data.get("event_type", "progress") not in EVENT_TYPES[:-1]:
            fail("invalid_input", "Use task accept for acceptance events")

        def action():
            eid = add_event(store, data)
            result = update_task(store, data) if any(k in data for k in OWNER_FIELDS) else {}
            return {**result, "event_id": eid}
    else:
        fail("invalid_input", "Unknown modification", command=command)
    return store.write(command, data, action)
