"""Generate a fully synthetic, repeatable relay demo using real CLI processes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

CLI = Path(__file__).resolve().parents[1] / "tools/relay"


def run(project, *command, body=None, cli=CLI):
    cmd = [sys.executable, str(cli), "--project", str(project), "--json", *command]
    if body is not None:
        cmd += ["--input-file", "-"]
        body = {"request_id": str(uuid.uuid4()), **body}
    p = subprocess.run(cmd, input=json.dumps(body, ensure_ascii=False) if body is not None else None,
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return json.loads(p.stdout)["data"]


def demo(output):
    output = output.resolve()
    if output.exists():
        raise RuntimeError("Demo output must be a new directory; existing files will not be overwritten")
    output.mkdir(parents=True)
    project = output / "project"
    run(project, "init", body={"name": "合成接力示例", "goal": "由两个 CLI 会话接力生成示例成果",
                              "scope": "仅合成数据，不代表真实 harness 集成验收",
                              "working_agreements": "先读后写、领取、证据、回读、显式验收"})
    tid = run(project, "task", "create", body={"title": "制作示例成果", "objective": "完成一份可校验文本",
              "acceptance_criteria": "文本内容完整，SHA256 可核验，交接可续接"})["task_id"]
    a = run(project, "session", "start", body={"environment": "demo-cli-A"})["session_id"]
    claim = run(project, "claim", body={"task_id": tid, "session_id": a})
    run(project, "progress", body={"task_id": tid, "session_id": a, "generation": claim["generation"],
        "expected_revision": 1, "event_type": "progress", "content": "A 完成第一部分", "status": "in_progress",
        "current_summary": "已确认合成输出格式", "next_step": "由 B 生成并验证成果"})
    run(project, "decision", "add", body={"statement": "示例只使用合成内容", "rationale": "避免真实信息进入示例",
        "provenance": "verified_fact", "verification_method": "本脚本使用固定合成字符串"})
    run(project, "release", body={"task_id": tid, "session_id": a, "generation": claim["generation"]})
    handoff = run(project, "handoff", "--task", tid)["prompt"].replace(str(project), "<PROJECT_ROOT>")
    (project / "artifacts/handoff.md").write_text(handoff + "\n", encoding="utf-8")
    b = run(project, "session", "start", body={"environment": "demo-cli-B"})["session_id"]
    run(project, "context", "--task", tid)
    claim = run(project, "claim", body={"task_id": tid, "session_id": b})
    content = "Relay 合成示例成果：接力已完成。\n"
    result = project / "artifacts/result.txt"
    result.write_text(content, encoding="utf-8")
    evidence = run(project, "evidence", "add", body={"kind": "project_file", "locator": "artifacts/result.txt",
        "description": "合成成果", "digest": hashlib.sha256(result.read_bytes()).hexdigest()})["evidence_id"]
    progress = run(project, "progress", body={"task_id": tid, "session_id": b, "generation": claim["generation"],
        "expected_revision": 2, "event_type": "result", "content": "B 已生成成果并核验摘要", "evidence_refs": [evidence],
        "current_summary": "成果已生成并通过 SHA256 检查", "status": "awaiting_review",
        "next_step": "等待显式验收", "blocker": ""})
    run(project, "event", "show", "--id", progress["event_id"])
    run(project, "release", body={"task_id": tid, "session_id": b, "generation": claim["generation"]})
    run(project, "task", "accept", body={"task_id": tid, "session_id": b, "expected_revision": 3,
        "confirmation_source": "合成验收夹具；不代表真实用户批准", "note": "固定示例的输出、证据与状态检查通过"})
    final_task = run(project, "task", "show", "--task", tid)
    assert final_task["status"] == "done"
    run(project, "report", "--output", str(project / "artifacts/report.html"), body={})
    for harness in ("generic", "codex", "claude"):
        rendered = run(project, "integration", "render", "--harness", harness)
        if rendered["entry_file"]:
            (project / rendered["entry_file"]).write_text(rendered["snippet"], encoding="utf-8")
    preview = run(project, "export", "--kind", "full", "--quiesced", "--output", str(output / "full.zip"),
                  "--include", "artifacts/result.txt", "--include", "artifacts/handoff.md",
                  "--include", "artifacts/report.html", "--dry-run", body={})
    run(project, "export", "--kind", "full", "--quiesced", "--output", str(output / "full.zip"),
        "--include", "artifacts/result.txt", "--include", "artifacts/handoff.md",
        "--include", "artifacts/report.html", body={})
    restored = output / "restored"
    run(project, "import", "--archive", str(output / "full.zip"), "--destination", str(restored), body={})
    checked = run(restored, "doctor", cli=restored / "tools/relay")
    assert checked["ok"]
    assert run(restored, "task", "show", "--task", tid)["status"] == "done"
    return {"project": str(project), "restored": str(restored), "task_id": tid, "status": "done",
            "doctor": checked["ok"], "preview_file_count": len(preview["files"]),
            "evidence_layer": "two CLI sessions, not two real harnesses"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(demo(args.output), ensure_ascii=False, indent=2))
