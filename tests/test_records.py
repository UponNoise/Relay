import hashlib
from pathlib import Path
from test_basic import CLITest


class RecordTests(CLITest):
    def test_task_context_includes_project_decisions_and_events(self):
        tid, other, sid = self.task(), self.task(), self.session()
        old = self.call("decision", "add", data=self.data(statement="old", rationale="old",
                       provenance="agent_proposed"))["data"]["decision_id"]
        new = self.call("decision", "add", data=self.data(statement="PROJECT RULE", rationale="confirmed",
                       provenance="user_confirmed", confirmation_reference="synthetic approval", supersedes=old))["data"]["decision_id"]
        own = self.call("decision", "add", data=self.data(task_id=tid, statement="TASK RULE", rationale="local",
                       provenance="unverified"))["data"]["decision_id"]
        self.call("decision", "add", data=self.data(task_id=other, statement="OTHER RULE", rationale="other",
                  provenance="agent_proposed"))
        self.call("progress", data=self.data(session_id=sid, content="PROJECT EVENT"))
        ctx = self.call("context", "--task", tid)["data"]
        self.assertEqual({x["decision_id"] for x in ctx["collections"]["decisions"]}, {new, own})
        self.assertTrue(any(x["content"] == "PROJECT EVENT" for x in ctx["collections"]["events"]))
        handoff = self.call("handoff", "--task", tid)["data"]["prompt"]
        self.assertIn("PROJECT RULE", handoff)
        self.assertNotIn("OTHER RULE", handoff)

    def test_decisions_and_provenance(self):
        self.call("decision", "add", data=self.data(statement="x", rationale="y", provenance="verified_fact"), code="invalid_input")
        first = self.call("decision", "add", data=self.data(statement="proposal", rationale="small",
                                                            provenance="agent_proposed"))["data"]["decision_id"]
        second = self.call("decision", "add", data=self.data(statement="checked", rationale="observed",
                                                             provenance="verified_fact", verification_method="synthetic test",
                                                             supersedes=first))["data"]["decision_id"]
        rows = self.call("context")["data"]["collections"]["decisions"]
        self.assertEqual([r["decision_id"] for r in rows], [second])
        self.assertEqual(len(self.call("decision", "list")["data"]), 2)

    def test_evidence_digest_and_missing(self):
        p = self.root / "artifacts/result.txt"
        p.write_text("synthetic", encoding="utf-8")
        eid = self.call("evidence", "add", data=self.data(kind="project_file", locator="artifacts/result.txt",
                                                         description="output", digest=hashlib.sha256(b"synthetic").hexdigest()))["data"]["evidence_id"]
        self.assertTrue(self.call("evidence", "check", "--id", eid)["data"][0]["ok"])
        p.write_text("changed")
        self.assertFalse(self.call("evidence", "check", "--id", eid)["data"][0]["ok"])
        self.call("evidence", "add", data=self.data(kind="project_file", locator="../private", description="bad"), code="invalid_input")

    def test_external_mapping_and_local_replay(self):
        eid = self.call("evidence", "add", data=self.data(kind="external_file", locator="resource:assets/item.txt",
                                                         description="external"))["data"]["evidence_id"]
        self.assertFalse(self.call("evidence", "check", "--id", eid)["data"][0]["ok"])
        external = Path(self.tmp.name) / "external"
        external.mkdir()
        (external / "item.txt").write_text("fixture")
        data = self.data(resources={"assets": str(external)}, environment="new-host")
        result = self.call("local", "set", data=data)
        self.assertEqual(self.call("local", "set", data=data), result)
        self.call("local", "set", data={**data, "environment": "changed"}, code="duplicate_request_mismatch")
        self.assertTrue(self.call("evidence", "check", "--id", eid)["data"][0]["ok"])

    def test_handoff_limits_and_integration_preserves_entry(self):
        tid = self.task()
        sid = self.session()
        for n in range(3):
            self.call("progress", data=self.data(task_id=tid, session_id=sid, content=str(n)))
        ctx = self.call("context", "--limit", "1")["data"]
        self.assertTrue(ctx["truncated"]["events"])
        handoff = self.call("handoff", "--task", tid)["data"]["prompt"]
        self.assertIn("接入已有项目", handoff)
        self.assertIn(tid, handoff)
        entry = self.root / "AGENTS.md"
        entry.write_text("existing")
        self.call("integration", "render", "--harness", "codex")
        self.assertEqual(entry.read_text(), "existing")
        self.assertTrue(self.call("integration", "check", "--harness", "codex")["data"]["cli_available"])
        self.assertFalse(self.call("integration", "check", "--harness", "claude")["data"]["automatic_loading_verified"])
