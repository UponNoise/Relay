"""Decisions and immutable evidence references."""
from common import canonical, fail, fields, now, require, uid
from resources import validate_evidence


def action_for(store, command, data):
    if command == "decision add":
        fields(data, ("task_id", "statement", "rationale", "provenance", "confirmation_reference",
                      "supersedes", "verification_method", "evidence_refs"),
               ("statement", "rationale", "provenance"))
        if data["provenance"] not in ("user_confirmed", "agent_proposed", "verified_fact", "unverified"):
            fail("invalid_input", "Invalid decision provenance")
        if data["provenance"] == "user_confirmed":
            require(data, "confirmation_reference")
        refs = data.get("evidence_refs", [])
        if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
            fail("invalid_input", "evidence_refs must be evidence IDs")
        if data["provenance"] == "verified_fact" and not refs and not data.get("verification_method"):
            fail("invalid_input", "verified_fact requires evidence or verification_method")
        if "verification_method" in data:
            require(data, "verification_method")

        def action():
            if data.get("task_id"):
                store.get("tasks", "task_id", data["task_id"])
            for ref in refs:
                store.get("evidence", "evidence_id", ref)
            if data.get("supersedes"):
                store.get("decisions", "decision_id", data["supersedes"])
                if store.db.execute("SELECT 1 FROM decisions WHERE supersedes=?", (data["supersedes"],)).fetchone():
                    fail("invalid_input", "Decision has already been superseded")
            did = uid()
            reference = data.get("confirmation_reference", "")
            if data.get("verification_method") or refs:
                reference = canonical({"confirmation_reference": reference,
                                       "verification_method": data.get("verification_method", ""), "evidence_refs": refs})
            store.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?)",
                             (did, store.project()["project_id"], data.get("task_id"), data["statement"],
                              data["rationale"], data["provenance"], reference, data.get("supersedes"), now()))
            return {"decision_id": did}
        return action
    if command == "evidence add":
        validate_evidence(store, data)

        def action():
            eid = uid()
            store.db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?)",
                             (eid, data["kind"], data["locator"], data["description"], data.get("digest"),
                              data.get("verification_method"), data.get("verified_at")))
            return {"evidence_id": eid}
        return action
    return None
