"""argparse interface. JSON errors never contain a Python traceback."""
import argparse
import json
import sqlite3
import sys

from common import RelayError, VERSION, fail
from service import mutate
from store import Store, discover, initialize
from views import query

COMMANDS = {
    "init": None, "status": None, "context": None, "progress": None,
    "project": ("show", "update"), "task": ("create", "list", "show", "update", "accept"),
    "session": ("start", "show"), "claim": None, "release": None, "recover": None,
    "event": ("show",),
    "decision": ("add", "list"), "evidence": ("add", "check"), "handoff": None,
    "integration": ("render", "check"), "local": ("show", "set"),
    "export": None, "import": None, "doctor": None, "report": None,
}
WRITES = {"task create", "project update", "progress", "session start", "claim", "release", "recover", "task update", "task accept"}
WRITES.update({"decision add", "evidence add"})


class Parser(argparse.ArgumentParser):
    def error(self, message):
        fail("invalid_input", message)


def options(parser):
    # Suppressed defaults let shared options appear before or after subcommands.
    parser.add_argument("--project", default=argparse.SUPPRESS, help="Project root")
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="JSON only on stdout")
    parser.add_argument("--input-file", default=argparse.SUPPRESS, help="JSON file, or - for stdin")
    parser.add_argument("--task", default=argparse.SUPPRESS, help="Task UUID")
    parser.add_argument("--id", default=argparse.SUPPRESS, help="Object UUID")
    parser.add_argument("--since", default=argparse.SUPPRESS, help="ISO timestamp lower bound")
    parser.add_argument("--limit", type=int, default=argparse.SUPPRESS)
    parser.add_argument("--offset", type=int, default=argparse.SUPPRESS)
    parser.add_argument("--harness", choices=("generic", "codex", "claude"), default=argparse.SUPPRESS)
    parser.add_argument("--kind", choices=("collaboration", "full"), default=argparse.SUPPRESS)
    parser.add_argument("--output", default=argparse.SUPPRESS)
    parser.add_argument("--include", action="append", default=argparse.SUPPRESS)
    parser.add_argument("--exclude", action="append", default=argparse.SUPPRESS)
    parser.add_argument("--quiesced", action="store_true", default=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS)
    parser.add_argument("--archive", default=argparse.SUPPRESS)
    parser.add_argument("--destination", default=argparse.SUPPRESS)


def parser():
    root = Parser(description="Relay: 本地离线项目协作", prog="relay")
    options(root)
    root.add_argument("--version", action="version", version=VERSION)
    subs = root.add_subparsers(dest="command", required=True)
    for name, children in COMMANDS.items():
        p = subs.add_parser(name)
        options(p)
        if children:
            cs = p.add_subparsers(dest="subcommand", required=True)
            for child in children:
                options(cs.add_parser(child))
    return root


def payload(args):
    if not args.input_file:
        fail("invalid_input", "Modification requires --input-file FILE (or - for stdin)")
    try:
        if args.input_file == "-":
            value = json.load(sys.stdin)
        else:
            with open(args.input_file, encoding="utf-8-sig") as handle:
                value = json.load(handle)
    except (ValueError, OSError) as exc:
        fail("invalid_input", "Invalid JSON input", reason=str(exc))
    if not isinstance(value, dict):
        fail("invalid_input", "Input must be a JSON object")
    return value


def dispatch(args):
    command = args.command + (" " + args.subcommand if getattr(args, "subcommand", None) else "")
    if command == "init":
        return initialize(args.project or ".", payload(args))
    if command == "integration render":
        from integration import render
        return render(args.harness)
    if command == "import":
        from packages import import_package
        return import_package(args, payload(args))
    store = Store(discover(args.project))
    try:
        if command == "export":
            from packages import export_package
            return export_package(store, args, payload(args))
        if command == "report":
            from health import report
            return report(store, args, payload(args))
        if command == "doctor":
            from health import doctor
            return doctor(store)
        if command == "local set":
            from resources import set_local
            return set_local(store, payload(args))
        if command in WRITES:
            return mutate(store, command, payload(args))
        return query(store, command, args)
    finally:
        store.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Windows pipes must preserve Chinese and multiline text without shell escaping.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    json_mode = "--json" in argv
    try:
        args = parser().parse_args(argv)
        for k, v in {"project": None, "json": False, "input_file": None, "task": None,
                     "id": None, "since": None, "limit": 20, "offset": 0, "harness": "generic",
                     "kind": "collaboration", "output": None, "include": [], "exclude": [],
                     "quiesced": False, "dry_run": False, "archive": None, "destination": None}.items():
            if not hasattr(args, k):
                setattr(args, k, v)
        result = dispatch(args)
        if args.json:
            print(json.dumps({"ok": True, "data": result}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RelayError, sqlite3.Error, OSError, ValueError) as exc:
        if not isinstance(exc, RelayError):
            code = "database_busy" if isinstance(exc, sqlite3.OperationalError) and ("locked" in str(exc) or "busy" in str(exc)) else "integrity_error"
            exc = RelayError(code, str(exc))
        error = {"ok": False, "error": {"code": exc.code, "message": exc.message, "details": exc.details}}
        if json_mode:
            print(json.dumps(error, ensure_ascii=False))
        else:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 3 if exc.code == "database_busy" else 4 if exc.code == "integrity_error" else 2
