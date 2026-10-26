"""Explicit, offline snapshot packages; no background synchronization."""
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import zipfile

from common import SCHEMA, VERSION, canonical, fail, fields, fingerprint, now, read_json, uid, write_json
from resources import hash_file, inside, relative_name
from store import Store, connect

MAX_FILE = 50 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
EXCLUDED_PARTS = {".git", ".relay", ".codex", ".agents", ".aws", ".ssh", ".venv", "venv",
                  "__pycache__", "node_modules", ".cache", "logs", "backups", "exports", "imports",
                  "private", "inputs", "transcripts", ".vscode", ".idea"}
EXCLUDED_PATTERNS = ("*.db", "*.db-*", "*.sqlite*", "*.log", "*.pyc", "*.tmp", "*.zip",
                     "*.pem", "*.key", ".env*", "*credentials*", "*secret*", "local.json", "*.local.*")


def excluded(name):
    p = relative_name(name)
    return any(x.lower() in EXCLUDED_PARTS for x in p.parts) or any(
        fnmatch.fnmatch(p.name.lower(), pat) for pat in EXCLUDED_PATTERNS)


def selected_files(store, kind, includes, excludes):
    if kind == "collaboration" and includes:
        fail("invalid_input", "Only full packages accept --include")
    result = {}
    for name in includes:
        path = inside(store.root, name)
        if excluded(name) or any(fnmatch.fnmatch(name, pattern) for pattern in excludes):
            continue
        if name.startswith("tools/relay/") or name in ("manifest.json", "evidence-index.json", "RESTORE.md"):
            fail("invalid_input", "Selected path is reserved", path=name)
        if not path.is_file():
            fail("missing_resource", "Select individual existing files, not directories", path=name)
        if path.stat().st_size > MAX_FILE:
            fail("invalid_input", "Selected file exceeds 50 MiB limit", path=name)
        result[name] = path
    return result


def integrity(db):
    rows = [r[0] for r in db.execute("PRAGMA integrity_check")]
    foreign = db.execute("PRAGMA foreign_key_check").fetchall()
    if rows != ["ok"] or foreign:
        fail("integrity_error", "Database integrity or foreign key check failed")


def export_package(store, args, data):
    fields(data, ())
    if not args.output:
        fail("invalid_input", "export requires --output")
    request = {**data, "kind": args.kind, "include": sorted(args.include), "exclude": sorted(args.exclude),
               "quiesced": args.quiesced, "output": str(Path(args.output).resolve())}
    fp = fingerprint("export", request)
    output = Path(args.output).resolve()
    if output.is_relative_to(store.root / ".relay") or output.is_relative_to(store.root / "tools/relay"):
        fail("invalid_input", "Output must not overwrite Relay metadata or source")
    prior = store.db.execute("SELECT * FROM requests WHERE request_id=?", (data["request_id"],)).fetchone()
    if prior:
        if prior["fingerprint"] != fp:
            fail("duplicate_request_mismatch", "Request ID already used with different input")
        result = json.loads(prior["result"])
        if not output.is_file() or hash_file(output) != result["sha256"]:
            fail("integrity_error", "Previously exported artifact is absent or changed")
        return result
    if output.exists():
        # Resume a completed file operation if its DB receipt was interrupted.
        try:
            with zipfile.ZipFile(output) as z:
                manifest = json.loads(z.read("manifest.json"))
        except (ValueError, KeyError, zipfile.BadZipFile):
            fail("invalid_input", "Output already exists; refusing to overwrite")
        if not isinstance(manifest, dict) or manifest.get("request_id") != data["request_id"] or manifest.get("request_fingerprint") != fp:
            fail("invalid_input", "Output already exists; use a new path")
        result = {"export_id": manifest["export_id"], "project_id": manifest["project_id"],
                  "revision": manifest["snapshot_revision"], "sha256": hash_file(output)}
        return store.write("export", request, lambda: result)

    selected = selected_files(store, args.kind, args.include, args.exclude)
    if args.kind == "full":
        if not args.quiesced:
            fail("invalid_input", "Full export requires --quiesced after stopping business work")
        if store.db.execute("SELECT 1 FROM claims WHERE session_id IS NOT NULL").fetchone():
            fail("claim_conflict", "Release all active claims before full export")
    files = {".relay/project.json": store.root / ".relay/project.json",
             ".relay/PROTOCOL.md": store.root / ".relay/PROTOCOL.md"}
    source = Path(__file__).parent
    for path in source.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".md") and "__pycache__" not in path.parts:
            files["tools/relay/" + path.relative_to(source).as_posix()] = path
    files.update(selected)
    if args.dry_run:
        return {"files": sorted([*files, ".relay/state.sqlite3", "manifest.json", "evidence-index.json", "RESTORE.md"]),
                "selected_files": sorted(selected), "excluded_inputs": sorted(set(args.include) - set(selected)),
                "warning": "Inspect this list for secrets; exclusions are not a secret detector."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="relay-export-", dir=output.parent) as tmp:
        tmp = Path(tmp)
        snap = tmp / "state.sqlite3"
        dest = connect(snap)
        try:
            store.db.backup(dest, pages=256, sleep=0.05)
            integrity(dest)
            project = dict(dest.execute("SELECT * FROM project").fetchone())
            if args.kind == "full" and dest.execute("SELECT 1 FROM claims WHERE session_id IS NOT NULL").fetchone():
                fail("claim_conflict", "A claim appeared during export")
            evidence = [dict(r) for r in dest.execute("SELECT * FROM evidence")]
        finally:
            dest.close()
        files[".relay/state.sqlite3"] = snap
        manifest = {"export_id": uid(), "project_id": project["project_id"], "source_instance_id": store.local["instance_id"],
                    "tool_version": VERSION, "schema_version": SCHEMA, "created_at": now(), "snapshot_revision": project["revision"],
                    "kind": args.kind, "request_id": data["request_id"], "request_fingerprint": fp, "files": [],
                    "external_resources": [{"evidence_id": e["evidence_id"], "locator": e["locator"], "included": False}
                                           for e in evidence if e["kind"] == "external_file"],
                    "omitted_project_files": [e["locator"] for e in evidence if e["kind"] == "project_file" and e["locator"] not in files]}
        frozen = {}
        archive = tmp / "package.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            total = 0
            for name, path in sorted(files.items()):
                before = path.stat()
                content = path.read_bytes()
                after = path.stat()
                digest = hashlib.sha256(content).hexdigest()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(content) != before.st_size:
                    fail("integrity_error", "File changed while exporting", path=name)
                total += len(content)
                if total > MAX_TOTAL:
                    fail("invalid_input", "Package exceeds 500 MiB")
                z.writestr(name, content)
                manifest["files"].append({"path": name, "size": len(content), "sha256": digest})
                if name in selected:
                    frozen[name] = (path, digest, after.st_mtime_ns)
            generated = {
                "evidence-index.json": canonical(evidence).encode("utf-8"),
                "RESTORE.md": ("# 恢复说明\n使用 python tools/relay import --archive 包路径 --destination 新目录 "
                               "--input-file 请求JSON。恢复后运行 local set、doctor、context。\n"
                               "快照不停止旧副本；迁移后旧副本停止写入；不能合并分叉。\n").encode("utf-8")}
            for name, content in generated.items():
                z.writestr(name, content)
                manifest["files"].append({"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, (path, digest, mtime) in frozen.items():
            if hash_file(path) != digest or path.stat().st_mtime_ns != mtime:
                fail("integrity_error", "File changed during packaging; no package delivered", path=name)
        if args.kind == "full" and store.project()["revision"] != project["revision"]:
            fail("integrity_error", "Project changed during full export; pause work and retry")
        # Exclusive hard link installs the completed file without overwriting a concurrent writer.
        os.link(archive, output)
    result = {"export_id": manifest["export_id"], "project_id": project["project_id"],
              "revision": project["revision"], "sha256": hash_file(output)}
    return store.write("export", request, lambda: result)


def validate_archive(archive, staging):
    try:
        z = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        fail("integrity_error", "Cannot read ZIP", reason=str(exc))
    with z:
        infos = z.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_TOTAL:
            fail("invalid_input", "Archive exceeds supported limits")
        names, folded = set(), set()
        for info in infos:
            relative_name(info.orig_filename)
            if info.orig_filename != info.filename:
                fail("invalid_input", "Archive member name was normalized")
            relative_name(info.filename)
            if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                fail("invalid_input", "Directory/link archive members are not supported")
            if info.filename in names or info.filename.casefold() in folded:
                fail("integrity_error", "Duplicate archive member")
            names.add(info.filename)
            folded.add(info.filename.casefold())
        try:
            manifest = json.loads(z.read("manifest.json"))
        except (KeyError, ValueError):
            fail("integrity_error", "Missing or invalid manifest")
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
            fail("incompatible_version", "Only schema 1 packages are supported")
        for key in ("export_id", "project_id", "source_instance_id", "tool_version", "created_at"):
            if not isinstance(manifest.get(key), str) or not manifest[key]:
                fail("integrity_error", "Missing manifest metadata", field=key)
        if type(manifest.get("snapshot_revision")) is not int or manifest.get("kind") not in ("full", "collaboration"):
            fail("integrity_error", "Invalid manifest snapshot metadata")
        if not isinstance(manifest.get("files"), list):
            fail("integrity_error", "Invalid manifest file list")
        expected = {}
        for row in manifest["files"]:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str):
                fail("integrity_error", "Invalid manifest entry")
            path = row["path"]
            if path in expected:
                fail("integrity_error", "Duplicate manifest entry")
            expected[path] = row
        if names != set(expected) | {"manifest.json"}:
            fail("integrity_error", "Manifest and archive file sets differ")
        required = {".relay/project.json", ".relay/state.sqlite3", ".relay/PROTOCOL.md",
                    "tools/relay/__main__.py", "evidence-index.json", "RESTORE.md"}
        if not required.issubset(names):
            fail("integrity_error", "Required package contents missing")
        for name in expected:
            if name.startswith(".relay/") and name not in required:
                fail("invalid_input", "Private or unsupported Relay metadata in package")
            if name == "local.json" or (not name.startswith((".relay/", "tools/relay/")) and excluded(name)):
                fail("invalid_input", "Excluded private file in archive", path=name)
            info = z.getinfo(name)
            row = expected[name]
            content = z.read(name)
            if row.get("size") != info.file_size or hashlib.sha256(content).hexdigest() != row.get("sha256"):
                fail("integrity_error", "File checksum mismatch", path=name)
            path = inside(staging, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return manifest


def import_package(args, data):
    fields(data, ())
    if not args.archive or not args.destination:
        fail("invalid_input", "import requires --archive and --destination")
    archive = Path(args.archive).resolve()
    target = Path(args.destination).absolute()
    if target.is_symlink() or target.resolve() != target:
        fail("invalid_input", "Restore destination must not traverse symlinks")
    digest = hash_file(archive)
    request = {**data, "archive_sha256": digest}
    fp = fingerprint("import", request)
    if target.exists() and any(target.iterdir()):
        receipt = target / ".relay/import-receipt.json"
        if receipt.is_file():
            record = read_json(receipt)
            if record.get("request_id") == data["request_id"]:
                if record.get("fingerprint") != fp:
                    fail("duplicate_request_mismatch", "Import request changed")
                return record["result"]
        fail("invalid_input", "Destination must be new or empty")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="relay-import-", dir=target.parent) as tmp:
        staging = Path(tmp) / "project"
        staging.mkdir()
        manifest = validate_archive(archive, staging)
        local = {"instance_id": uid(), "environment": "restored", "resources": {}}
        write_json(staging / ".relay/local.json", local)
        store = Store(staging)
        try:
            integrity(store.db)
            project = store.project()
            if project["project_id"] != manifest.get("project_id") or project["revision"] != manifest.get("snapshot_revision"):
                fail("integrity_error", "Snapshot identity or revision mismatch")
            store.db.execute("BEGIN IMMEDIATE")
            if store.db.execute("SELECT 1 FROM requests WHERE request_id=?", (data["request_id"],)).fetchone():
                fail("duplicate_request_mismatch", "Import request ID already exists in source history")
            claims = [dict(r) for r in store.db.execute("SELECT * FROM claims WHERE session_id IS NOT NULL")]
            store.db.execute("UPDATE claims SET session_id=NULL,generation=generation+1,updated_at=?", (now(),))
            store.db.execute("UPDATE sessions SET active=0")
            event_id = uid()
            store.db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                             (event_id, None, "handoff", canonical({"operation": "migration_restore",
                              "export_id": manifest["export_id"], "released_claims": claims, "new_instance_id": local["instance_id"]}),
                              "migration", None, now(), "[]", data["request_id"]))
            store.db.execute("UPDATE project SET revision=revision+1,updated_at=?", (now(),))
            result = {"project_id": project["project_id"], "instance_id": local["instance_id"], "event_id": event_id,
                      "revision": project["revision"] + 1, "request_id": data["request_id"],
                      "released_claims": len(claims), "unmapped_resources": manifest.get("external_resources", [])}
            store.db.execute("INSERT INTO requests VALUES (?,?,?)", (data["request_id"], fp, canonical(result)))
            store.db.commit()
            integrity(store.db)
        finally:
            store.close()
        write_json(staging / ".relay/import-receipt.json", {"request_id": data["request_id"], "fingerprint": fp, "result": result})
        (staging / "artifacts").mkdir(exist_ok=True)
        if target.exists():
            target.rmdir()  # Fails if anything appeared; never remove a nonempty directory.
        if target.exists():
            fail("invalid_input", "Destination appeared during import")
        staging.rename(target)
    return result
