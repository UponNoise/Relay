import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

CLI = Path(__file__).resolve().parents[1] / "tools/relay"


class CLITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="relay-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "中文 项目"
        self.init_data = self.data(name="合成项目", goal="测试\n多行目标")
        self.init = self.call("init", data=self.init_data)["data"]

    def data(self, **kwargs):
        return {"request_id": str(uuid.uuid4()), **kwargs}

    def run_cli(self, *args, data=None, cwd=None, project=True):
        cmd = [sys.executable, str(CLI), "--json"]
        if project:
            cmd += ["--project", str(self.root)]
        cmd += list(args)
        if data is not None:
            cmd += ["--input-file", "-"]
        return subprocess.run(cmd, input=json.dumps(data, ensure_ascii=False) if data is not None else None,
                              capture_output=True, text=True, encoding="utf-8", cwd=cwd, timeout=15)

    def call(self, *args, data=None, code=None, **kwargs):
        r = self.run_cli(*args, data=data, **kwargs)
        parsed = json.loads(r.stdout)
        self.assertEqual(r.stderr, "", r.stderr)
        if code:
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(parsed["error"]["code"], code)
        else:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return parsed

    def task(self):
        return self.call("task", "create", data=self.data(
            title="合成任务", objective="实现示例", acceptance_criteria="测试通过"))["data"]["task_id"]


class BasicTests(CLITest):
    def test_init_replay_and_refuse_overwrite(self):
        self.assertEqual(self.call("init", data=self.init_data)["data"], self.init)
        self.call("init", data=self.data(name="x", goal="y"), code="invalid_input")

    def test_task_event_context(self):
        tid = self.task()
        e = self.call("progress", data=self.data(task_id=tid, content="第一行\n第二行"))["data"]
        self.assertEqual(self.call("event", "show", "--id", e["event_id"])["data"]["content"], "第一行\n第二行")
        ctx = self.call("context")["data"]
        self.assertEqual(ctx["collections"]["tasks"][0]["task_id"], tid)
        self.assertEqual(ctx["project"]["goal"], "测试\n多行目标")

    def test_discover_and_other_cwd(self):
        child = self.root / "a/b"
        child.mkdir(parents=True)
        self.assertEqual(self.call("project", "show", cwd=child, project=False)["data"]["project_id"], self.init["project_id"])
        self.assertEqual(self.call("project", "show", cwd=self.tmp.name)["data"]["project_id"], self.init["project_id"])

    def test_mismatch(self):
        path = self.root / ".relay/project.json"
        m = json.loads(path.read_text())
        m["project_id"] = str(uuid.uuid4())
        path.write_text(json.dumps(m))
        self.call("status", code="project_mismatch")

    def test_nested_requires_explicit(self):
        child = self.root / "nested"
        r = self.run_cli("--project", str(child), "init", data=self.data(name="inner", goal="inner"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.call("context", cwd=child, project=False, code="project_mismatch")
        self.call("context", cwd=child)

    def test_json_errors_and_validation(self):
        self.call("task", "create", data=self.data(title="incomplete"), code="invalid_input")
        self.call("task", "show", "--task", "missing", code="not_found")
        self.call("unknown", code="invalid_input")
        self.call("task", "create", data=self.data(title="a", objective="b", acceptance_criteria="c", extra=True), code="invalid_input")

    def test_project_revision(self):
        result = self.call("project", "update", data=self.data(expected_revision=1, scope="有限范围"))["data"]
        self.assertEqual(result["revision"], 2)
        self.call("project", "update", data=self.data(expected_revision=1, scope="过期"), code="revision_conflict")


if __name__ == "__main__":
    unittest.main()
