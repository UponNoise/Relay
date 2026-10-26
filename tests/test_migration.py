import json
from pathlib import Path
import zipfile

from test_basic import CLITest


class MigrationTests(CLITest):
    def export(self, kind="collaboration", extra=()):
        out = Path(self.tmp.name) / (kind + ".zip")
        data = self.data()
        self.call("export", "--kind", kind, "--output", str(out), *extra, data=data)
        return out, data

    def restore(self, archive, name="restored", code=None, data=None):
        target = Path(self.tmp.name) / name
        result = self.call("import", "--archive", str(archive), "--destination", str(target),
                           data=data or self.data(), code=code)
        return target, result

    def test_collaboration_new_instance_and_identity(self):
        tid, sid = self.task(), self.session()
        self.call("claim", data=self.data(task_id=tid, session_id=sid))
        archive, data = self.export()
        replay = self.call("export", "--output", str(archive), data=data)
        self.assertTrue(replay["ok"])
        with zipfile.ZipFile(archive) as z:
            self.assertNotIn(".relay/local.json", z.namelist())
        request = self.data()
        target, result = self.restore(archive, data=request)
        self.assertEqual(result["data"]["project_id"], self.init["project_id"])
        self.assertNotEqual(result["data"]["instance_id"], self.init["instance_id"])
        self.assertEqual(result["data"]["released_claims"], 1)
        self.assertEqual(self.restore(archive, data=request)[1], result)
        self.call("--project", str(target), "task", "show", "--task", tid)
        self.call("--project", str(target), "claim", data=self.data(task_id=tid, session_id=sid), code="stale_claim")
        self.assertTrue(self.call("--project", str(target), "doctor")["data"]["ok"])

    def test_full_selection_and_active_claim(self):
        (self.root / "artifacts/result.txt").write_text("synthetic")
        (self.root / ".env").write_text("synthetic private marker")
        tid, sid = self.task(), self.session()
        claim = self.call("claim", data=self.data(task_id=tid, session_id=sid))["data"]
        out = Path(self.tmp.name) / "full.zip"
        args = ["export", "--kind", "full", "--output", str(out), "--include", "artifacts/result.txt", "--include", ".env"]
        self.call(*args, data=self.data(), code="invalid_input")
        self.call(*args, "--quiesced", data=self.data(), code="claim_conflict")
        self.call("release", data=self.data(task_id=tid, session_id=sid, generation=claim["generation"]))
        preview = self.call(*args, "--quiesced", "--dry-run", data=self.data())["data"]
        self.assertNotIn(".env", preview["files"])
        self.call(*args, "--quiesced", data=self.data())
        target, _ = self.restore(out)
        self.assertEqual((target / "artifacts/result.txt").read_text(), "synthetic")
        self.assertFalse((target / ".env").exists())

    def test_nonempty_destination(self):
        archive, _ = self.export()
        target = Path(self.tmp.name) / "occupied"
        target.mkdir()
        (target / "keep.txt").write_text("preserve")
        self.restore(archive, "occupied", code="invalid_input")
        self.assertEqual((target / "keep.txt").read_text(), "preserve")

    def test_bad_hash_traversal_and_schema(self):
        archive, _ = self.export()
        with zipfile.ZipFile(archive) as z:
            content = {n: z.read(n) for n in z.namelist()}
        for case in ("hash", "traversal", "schema"):
            items = dict(content)
            if case == "hash":
                items["RESTORE.md"] = b"tampered"
            elif case == "traversal":
                items["../escape"] = b"bad"
            else:
                m = json.loads(items["manifest.json"])
                m["schema_version"] = 999
                items["manifest.json"] = json.dumps(m).encode()
            bad = Path(self.tmp.name) / (case + ".zip")
            with zipfile.ZipFile(bad, "w") as z:
                for n, b in items.items():
                    z.writestr(n, b)
            code = {"hash": "integrity_error", "traversal": "invalid_input", "schema": "incompatible_version"}[case]
            target, _ = self.restore(bad, case + "-target", code=code)
            self.assertFalse(target.exists())

    def test_doctor_missing_and_html_escape(self):
        self.call("evidence", "add", data=self.data(kind="external_file", locator="resource:missing/file", description="missing"))
        self.assertFalse(self.call("doctor")["data"]["ok"])
        self.call("task", "create", data=self.data(title="<script>alert(1)</script>", objective="x", acceptance_criteria="y"))
        output = Path(self.tmp.name) / "report.html"
        request = self.data()
        result = self.call("report", "--output", str(output), data=request)
        self.assertEqual(self.call("report", "--output", str(output), data=request), result)
        text = output.read_text(encoding="utf-8")
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("https://", text)
