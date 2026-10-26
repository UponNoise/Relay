"""Integrity diagnostics and non-editable offline HTML."""
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile

from common import canonical, fail, fields, now
from packages import integrity
from resources import check_evidence
from views import rowdict


def doctor(store):
    integrity(store.db)
    checks = [check_evidence(store, dict(r)) for r in store.db.execute("SELECT * FROM evidence")]
    required = {name: (store.root / name).is_file()
                for name in (".relay/PROTOCOL.md", "tools/relay/__main__.py")}
    problems = [c for c in checks if not c["ok"]]
    return {"ok": not problems and all(required.values()), "project_id": store.project()["project_id"],
            "instance_id": store.local["instance_id"], "schema_version": store.project()["schema_version"],
            "database": "ok", "foreign_keys": "ok", "required_files": required, "evidence": checks,
            "missing_or_changed": problems, "note": "No network access; URLs are not fetched."}


def report(store, args, data):
    fields(data, ())
    if not args.output:
        fail("invalid_input", "report requires --output")
    output = Path(args.output).resolve()
    marker = hashlib.sha256(canonical(["report", store.project()["project_id"], data]).encode()).hexdigest()
    receipt_prefix = "<!-- relay-receipt:"
    if output.exists():
        text = output.read_text(encoding="utf-8")
        if text.startswith(receipt_prefix):
            receipt = json.loads(text.split("-->", 1)[0][len(receipt_prefix):])
            if receipt.get("marker") == marker:
                return receipt["result"]
        fail("invalid_input", "Report output already exists; use a new path")
    store.db.execute("BEGIN")
    try:
        project = store.project()
        snapshot = {t: [rowdict(r) for r in store.db.execute("SELECT * FROM " + t)]
                    for t in ("tasks", "decisions", "events", "evidence")}
    finally:
        store.db.rollback()
    result = {"project_id": project["project_id"], "revision": project["revision"], "request_id": data["request_id"]}
    # Receipt contains only encoded JSON; escape '<' to keep arbitrary request IDs out of markup.
    receipt = canonical({"marker": marker, "result": result}).replace("<", "\\u003c").replace(">", "\\u003e").replace("-", "\\u002d")
    parts = [receipt_prefix + receipt + "-->", "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Relay 项目快照</title>",
             "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#182c39;background:#f4f7fa}"
             "h1,h2{color:#12465d}article{background:white;padding:18px;margin:12px 0;border:1px solid #d4dfe5;border-radius:8px}"
             "pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#536874}</style><h1>Relay 项目快照</h1>",
             "<small>生成时间 " + html.escape(now()) + " · revision " + str(project["revision"]) + "</small>",
             "<h2>项目</h2><pre>" + html.escape(json.dumps(project, ensure_ascii=False, indent=2)) + "</pre>"]
    labels = {"tasks": "任务", "decisions": "决策", "events": "事件", "evidence": "证据"}
    for key, rows in snapshot.items():
        parts.append("<h2>" + labels[key] + "</h2>")
        for row in rows:
            parts.append("<article><pre>" + html.escape(json.dumps(row, ensure_ascii=False, indent=2)) + "</pre></article>")
    parts.append("</html>")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="relay-report-", dir=output.parent) as tmp:
        temp = Path(tmp) / "report.html"
        temp.write_text("\n".join(parts), encoding="utf-8")
        os.link(temp, output)
    return result
