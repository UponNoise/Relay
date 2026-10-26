"""Project-scoped snippets only; never edit harness configuration."""
from pathlib import Path
import subprocess
import sys

from common import fail

TARGETS = {"generic": None, "codex": "AGENTS.md", "claude": "CLAUDE.md"}


def render(harness):
    if harness not in TARGETS:
        fail("invalid_input", "Choose generic, codex or claude")
    text = (Path(__file__).parent / "templates" / (harness + ".md")).read_text(encoding="utf-8")
    return {"harness": harness, "entry_file": TARGETS[harness], "snippet": text,
            "instruction": "Manually merge this snippet into the project entry; preserve all existing content."}


def check(store, harness):
    snippet = render(harness)
    entry = store.root / snippet["entry_file"] if snippet["entry_file"] else None
    cli = store.root / "tools/relay"
    result = subprocess.run([sys.executable, str(cli), "--help"], capture_output=True, timeout=10)
    entry_exists = entry is None or entry.is_file()
    marker_present = bool(entry and entry.is_file() and "Relay" in entry.read_text(encoding="utf-8-sig"))
    return {"ok": result.returncode == 0 and entry_exists and (store.root / ".relay/PROTOCOL.md").is_file(),
            "entry_file": snippet["entry_file"], "entry_exists": entry_exists, "relay_marker_present": marker_present,
            "cli_available": result.returncode == 0, "automatic_loading_verified": False,
            "note": "Only files, paths and CLI checked; verify loading in a new real harness session."}
