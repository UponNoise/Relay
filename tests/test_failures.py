"""Additional behavioral failures required by the delivery spec."""
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import sys
import zipfile
from types import SimpleNamespace
from unittest import mock

from test_basic import CLITest, CLI

sys.path.insert(0, str(CLI))
from common import RelayError
from packages import export_package
from store import Store


class FailureTests(CLITest):
    def make_archive(self):
        archive = Path(self.tmp.name) / "valid.zip"
        self.call("export", "--output", str(archive), data=self.data())
        with zipfile.ZipFile(archive) as z:
            return {n: z.read(n) for n in z.namelist()}

    def bad_archive(self, items, suffix):
        path = Path(self.tmp.name) / (suffix + ".zip")
        with zipfile.ZipFile(path, "w") as z:
            for name, value in items.items():
                z.writestr(name, value)
        return path

    def reject(self, path, code):
        target = Path(self.tmp.name) / "destination"
        self.call("import", "--archive", str(path), "--destination", str(target),
                  data=self.data(), code=code)
        self.assertFalse(target.exists())

    def test_absolute_windows_and_duplicate_members(self):
        original = self.make_archive()
        for index, name in enumerate(("/escape", "C:/escape", "a/../../escape", "a\\escape")):
            archive = self.bad_archive({**original, name: b"bad"}, str(index))
            # Windows ZipInfo normalizes backslashes on creation. Restore the hostile
            # raw member name in both headers to test an archive received externally.
            if chr(92) in name:
                archive.write_bytes(archive.read_bytes().replace(b"a/escape", bytes([97, 92]) + b"escape"))
            self.reject(archive, "invalid_input")
        items = {**original, "RESTORE.MD": b"alias"}
        self.reject(self.bad_archive(items, "casealias"), "integrity_error")

    def test_symlink_member(self):
        archive = Path(self.tmp.name) / "symlink.zip"
        with zipfile.ZipFile(archive, "w") as z:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "../outside")
        self.reject(archive, "invalid_input")

    def test_missing_manifest_metadata_is_structured_error(self):
        items = self.make_archive()
        manifest = json.loads(items["manifest.json"])
        del manifest["export_id"]
        items["manifest.json"] = json.dumps(manifest).encode()
        self.reject(self.bad_archive(items, "missing-id"), "integrity_error")

    def test_database_identity_and_foreign_key_integrity(self):
        original = self.make_archive()
        for kind in ("identity", "foreign"):
            items = dict(original)
            if kind == "identity":
                meta = json.loads(items[".relay/project.json"])
                meta["project_id"] = "wrong"
                items[".relay/project.json"] = json.dumps(meta).encode()
                changed = ".relay/project.json"
                code = "project_mismatch"
            else:
                dbfile = Path(self.tmp.name) / "broken.sqlite3"
                dbfile.write_bytes(items[".relay/state.sqlite3"])
                db = sqlite3.connect(dbfile)
                db.execute("INSERT INTO claims VALUES ('unknown-task',NULL,1,'now')")
                db.commit()
                db.close()
                items[".relay/state.sqlite3"] = dbfile.read_bytes()
                changed = ".relay/state.sqlite3"
                code = "integrity_error"
            manifest = json.loads(items["manifest.json"])
            for row in manifest["files"]:
                if row["path"] == changed:
                    row["sha256"] = hashlib.sha256(items[changed]).hexdigest()
                    row["size"] = len(items[changed])
            items["manifest.json"] = json.dumps(manifest).encode()
            self.reject(self.bad_archive(items, kind), code)

    def test_file_changes_during_packaging(self):
        file = self.root / "artifacts/data.txt"
        file.write_text("before")
        output = Path(self.tmp.name) / "changed.zip"
        args = SimpleNamespace(output=str(output), kind="full", include=["artifacts/data.txt"],
                               exclude=[], quiesced=True, dry_run=False)
        store = Store(self.root)
        self.addCleanup(store.close)
        original = zipfile.ZipFile.writestr

        def change_after_read(z, name, content, *args, **kwargs):
            result = original(z, name, content, *args, **kwargs)
            if name == "artifacts/data.txt":
                file.write_text("changed externally")
            return result

        with mock.patch.object(zipfile.ZipFile, "writestr", change_after_read):
            with self.assertRaises(RelayError) as caught:
                export_package(store, args, self.data())
        self.assertEqual(caught.exception.code, "integrity_error")
        self.assertFalse(output.exists())

    def test_nonowner_cannot_change_summary_but_can_append(self):
        tid, sid, other = self.task(), self.session(), self.session()
        claim = self.call("claim", data=self.data(task_id=tid, session_id=sid))["data"]
        self.call("progress", data=self.data(task_id=tid, session_id=other, generation=claim["generation"],
                  expected_revision=1, content="must rollback", current_summary="unauthorized"), code="stale_claim")
        self.call("progress", data=self.data(task_id=tid, session_id=other, content="suggestion"))
        events = self.call("context", "--task", tid)["data"]["collections"]["events"]
        self.assertNotIn("must rollback", [e["content"] for e in events])
        self.assertIn("suggestion", [e["content"] for e in events])

    def test_input_file_and_since_filter(self):
        file = Path(self.tmp.name) / "请求 输入.json"
        file.write_text(json.dumps(self.data(title="文件\n输入", objective="目标", acceptance_criteria="验收"),
                                   ensure_ascii=False), encoding="utf-8-sig")
        self.call("task", "create", "--input-file", str(file))
        sid = self.session()
        self.call("progress", data=self.data(session_id=sid, content="earlier"))
        event = self.call("progress", data=self.data(session_id=sid, content="later"))["data"]
        recorded = self.call("event", "show", "--id", event["event_id"])["data"]["recorded_at"]
        context = self.call("context", "--since", recorded)["data"]
        self.assertEqual([e["content"] for e in context["collections"]["events"]], ["later"])
        self.call("context", "--since", "invalid", code="invalid_input")

    def test_replay_after_takeover_returns_original_success(self):
        tid, sid = self.task(), self.session()
        claim_data = self.data(task_id=tid, session_id=sid)
        first = self.call("claim", data=claim_data)
        self.call("recover", data=self.data(task_id=tid, session_id=self.session(), reason="synthetic interruption"))
        self.assertEqual(self.call("claim", data=claim_data), first)

    def test_unknown_schema_and_malformed_archive(self):
        path = self.root / ".relay/project.json"
        meta = json.loads(path.read_text())
        meta["schema_version"] = 999
        path.write_text(json.dumps(meta))
        self.call("context", code="incompatible_version")
        broken = Path(self.tmp.name) / "malformed.zip"
        broken.write_bytes(b"not a ZIP")
        self.reject(broken, "integrity_error")
