import json
import sqlite3
import subprocess
import sys
import time
from test_basic import CLITest, CLI


class ConsistencyTests(CLITest):
    def held(self):
        tid, sid = self.task(), self.session()
        claim = self.call("claim", data=self.data(task_id=tid, session_id=sid))["data"]
        return tid, sid, claim["generation"]

    def update(self, tid, sid, gen, revision=1, **extra):
        return self.data(task_id=tid, session_id=sid, generation=gen, expected_revision=revision, **extra)

    def test_process_race(self):
        tid = self.task()
        sessions = [self.session(), self.session()]
        procs = []
        for sid in sessions:
            p = subprocess.Popen([sys.executable, str(CLI), "--project", str(self.root), "--json",
                                  "claim", "--input-file", "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding="utf-8")
            p.stdin.write(json.dumps(self.data(task_id=tid, session_id=sid)))
            p.stdin.close()
            procs.append(p)
        results = []
        for p in procs:
            results.append(json.loads(p.stdout.read()))
            self.assertEqual(p.stderr.read(), "")
            p.wait(timeout=10)
            p.stdout.close()
            p.stderr.close()
        self.assertEqual(sum(r["ok"] for r in results), 1)
        self.assertEqual([r["error"]["code"] for r in results if not r["ok"]], ["claim_conflict"])
        self.assertEqual(self.call("task", "show", "--task", tid)["data"]["status"], "todo")

    def test_replay_before_revision_and_atomic_failure(self):
        tid, sid, gen = self.held()
        data = self.update(tid, sid, gen, content="result", current_summary="new", status="in_progress")
        first = self.call("progress", data=data)["data"]
        self.assertEqual(self.call("progress", data=data)["data"], first)
        self.call("progress", data={**data, "content": "changed"}, code="duplicate_request_mismatch")
        self.call("progress", data=self.update(tid, sid, gen, content="must rollback", current_summary="old"), code="revision_conflict")
        context = self.call("context", "--task", tid)["data"]
        events = context["collections"]["events"]
        self.assertEqual(sum(e["content"] == "result" for e in events), 1)
        self.assertFalse(any(e["content"] == "must rollback" for e in events))
        self.assertEqual(self.call("task", "show", "--task", tid)["data"]["current_summary"], "new")

    def test_recover_fences_old_owner(self):
        tid, sid, gen = self.held()
        other = self.session()
        self.call("recover", data=self.data(task_id=tid, session_id=other), code="invalid_input")
        claim = self.call("recover", data=self.data(task_id=tid, session_id=other, reason="explicit takeover"))["data"]
        self.assertGreater(claim["generation"], gen)
        self.call("task", "update", data=self.update(tid, sid, gen, current_summary="stale"), code="stale_claim")
        self.call("release", data=self.data(task_id=tid, session_id=sid, generation=gen), code="stale_claim")
        self.call("progress", data=self.data(task_id=tid, session_id=sid, content="suggestion", event_type="suggestion"))
        self.call("task", "update", data=self.update(tid, other, claim["generation"], current_summary="valid"))

    def test_acceptance_and_release(self):
        tid, sid, gen = self.held()
        self.call("task", "update", data=self.update(tid, sid, gen, status="done"), code="invalid_input")
        self.call("task", "update", data=self.update(tid, sid, gen, status="awaiting_review"))
        self.call("release", data=self.data(task_id=tid, session_id=sid, generation=gen))
        self.assertEqual(self.call("task", "show", "--task", tid)["data"]["status"], "awaiting_review")
        self.call("task", "accept", data=self.data(task_id=tid, session_id=sid, expected_revision=2,
                                                  confirmation_source="synthetic user confirmation", note="meets criteria"))
        self.assertEqual(self.call("task", "show", "--task", tid)["data"]["status"], "done")
        self.call("claim", data=self.data(task_id=tid, session_id=sid), code="invalid_input")

    def test_busy_is_bounded(self):
        db = sqlite3.connect(self.root / ".relay/state.sqlite3")
        try:
            db.execute("BEGIN IMMEDIATE")
            start = time.monotonic()
            self.call("task", "create", data=self.data(title="x", objective="y", acceptance_criteria="z"), code="database_busy")
            self.assertLess(time.monotonic() - start, 5)
        finally:
            db.rollback()
            db.close()
