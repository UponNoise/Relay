"""Read-only projections; SQLite remains authoritative."""
import json

from common import fail, now


def rowdict(row):
    result = dict(row)
    if "evidence_refs" in result:
        result["evidence_refs"] = json.loads(result["evidence_refs"])
    return result


def context(store, task=None, since=None, limit=20, offset=0):
    if not 1 <= limit <= 200 or offset < 0:
        fail("invalid_input", "limit must be 1..200; offset must be nonnegative")
    if task:
        store.get("tasks", "task_id", task)
    result = {"project": store.project(), "generated_at": now(), "collections": {}, "truncated": {}}
    for table in ("tasks", "decisions", "events", "evidence"):
        where, args = [], []
        if task and table in ("tasks", "decisions", "events"):
            where.append("task_id=?")
            args.append(task)
        if not task and table == "tasks":
            where.append("status NOT IN ('done','cancelled')")
        timecol = {"tasks": "updated_at", "decisions": "created_at", "events": "recorded_at"}.get(table)
        if since and timecol:
            where.append(f"{timecol}>=?")
            args.append(since)
        if table == "decisions":
            where.append("decision_id NOT IN (SELECT supersedes FROM decisions WHERE supersedes IS NOT NULL)")
        sql = "SELECT * FROM " + table + (" WHERE " + " AND ".join(where) if where else "")
        sql += f" ORDER BY {timecol or 'evidence_id'} DESC, rowid DESC LIMIT ? OFFSET ?"
        rows = store.db.execute(sql, (*args, limit + 1, offset)).fetchall()
        result["collections"][table] = [rowdict(r) for r in rows[:limit]]
        result["truncated"][table] = len(rows) > limit
    result["claims"] = [dict(r) for r in store.db.execute(
        "SELECT c.*,s.environment,s.last_activity FROM claims c LEFT JOIN sessions s USING(session_id) WHERE c.session_id IS NOT NULL")]
    result["continuation"] = {"next_offset": offset + limit, "instruction": "Use --offset with --limit; task show includes terminal tasks."}
    return result


def query(store, command, args):
    if command == "local show":
        return {k: v for k, v in store.local.items() if k != "_requests"}
    if command == "decision list":
        sql = "SELECT * FROM decisions"
        params = []
        if args.id:
            sql += " WHERE decision_id=?"
            params = [args.id]
        elif args.task:
            sql += " WHERE task_id=?"
            params = [args.task]
        return [dict(r) for r in store.db.execute(sql + " ORDER BY created_at", params)]
    if command == "evidence check":
        from resources import check_evidence
        items = [store.get("evidence", "evidence_id", args.id)] if args.id else [dict(r) for r in store.db.execute("SELECT * FROM evidence")]
        return [check_evidence(store, e) for e in items]
    if command == "integration check":
        from integration import check
        return check(store, args.harness)
    if command == "handoff":
        ctx = context(store, args.task, args.since, args.limit, args.offset)
        prompt = ("接入已有项目；这是生成时快照，必须重新查询最新状态。\n"
                  + "项目 ID：" + ctx["project"]["project_id"] + "\n本机根目录：" + str(store.root)
                  + "\n路径以目标电脑实际根目录为准。不要重复初始化或创建已有任务。\n"
                  + "先读 .relay/PROTOCOL.md，运行 python tools/relay context --json。\n"
                  + "创建自己的 session start；读取 task show 后 claim，已有负责人则沟通或显式 recover 并说明原因。\n"
                  + "先读后写，progress 记录结果/证据/下一步；按返回 ID 回读；交付 awaiting_review，用户明确确认后 accept。\n"
                  + json.dumps(ctx, ensure_ascii=False, indent=2))
        return {"prompt": prompt, "snapshot_revision": ctx["project"]["revision"]}
    if command == "session show":
        return store.get("sessions", "session_id", args.id)
    if command == "project show":
        return store.project()
    if command == "task show":
        result = store.get("tasks", "task_id", args.task or args.id)
        claim = store.db.execute("SELECT * FROM claims WHERE task_id=?", (result["task_id"],)).fetchone()
        result["claim"] = dict(claim) if claim else None
        return result
    if command == "event show":
        return rowdict(store.get("events", "event_id", args.id))
    if command == "task list":
        return [dict(r) for r in store.db.execute("SELECT * FROM tasks ORDER BY created_at")]
    if command in ("context", "status"):
        return context(store, args.task, args.since, args.limit, args.offset)
    fail("invalid_input", "Unknown query", command=command)
