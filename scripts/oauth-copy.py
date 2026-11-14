#!/usr/bin/env python3
"""
Copy a Google OAuth client value to the Windows clipboard so it can be pasted
into n8n without typing it by hand.

Usage:
    python3 scripts/oauth-copy.py id        # copies client_id
    python3 scripts/oauth-copy.py secret    # copies client_secret

By default it uses the newest client_secret_*.json in your Windows Downloads
folder. Pass a file path to use a specific one.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_newest() -> Path:
    candidates = []
    for folder in [Path.home() / "Downloads", *Path("/mnt/c/Users").glob("*/Downloads")]:
        if folder.is_dir():
            candidates += [Path(p) for p in glob.glob(str(folder / "client_secret_*.json"))]
    if not candidates:
        fail("no client_secret_*.json found in Downloads — download it from "
             "Google Cloud Console → Credentials → your OAuth client → Download JSON")
    return max(candidates, key=os.path.getmtime)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("id", "secret"):
        fail("usage: python3 scripts/oauth-copy.py id|secret [path-to-json]")

    which = sys.argv[1]
    path = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else find_newest()
    if not path.is_file():
        fail(f"file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    web = data.get("web", data)
    value = str(web.get("client_id" if which == "id" else "client_secret") or "")
    if not value:
        fail(f"no client_{which} in {path.name}")

    clip = shutil.which("clip.exe")
    if not clip:
        fail("clip.exe not found — run this from WSL with Windows interop enabled")
    subprocess.run([clip], input=value.encode("utf-16le"), check=True)

    label = "Client ID" if which == "id" else "Client secret"
    if which == "id":
        print(f"{label} copied to the Windows clipboard:\n  {value}\n")
    else:
        print(f"{label} copied to the Windows clipboard ({value[:7]}..., {len(value)} chars)\n")
    print(f"source: {path.name}")


if __name__ == "__main__":
    main()
