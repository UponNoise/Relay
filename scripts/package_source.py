"""Package only the reviewed Git index into a portable source ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    output = output.resolve()
    if output.exists():
        raise RuntimeError("Output exists; refusing to overwrite")
    paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"]).decode("utf-8").split("\0")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(filter(None, paths)):
            # Always use reviewed index bytes, never ignored or unrelated working files.
            content = subprocess.check_output(["git", "-C", str(ROOT), "show", ":" + name])
            z.writestr(name, content)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(digest + "  " + output.name + "\n", encoding="ascii")
    return {"archive": str(output), "sha256": digest, "files": len(list(filter(None, paths)))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
