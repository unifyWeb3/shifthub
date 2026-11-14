#!/usr/bin/env python3
"""
Create a ShiftHub credential in the local n8n instance without typing secrets
into the n8n UI, then wire it into every matching workflow node.

Usage:
    python3 scripts/add-credential.py telegram
    python3 scripts/add-credential.py smtp
    python3 scripts/add-credential.py imap

It prompts for the secret values (nothing is echoed, nothing is saved to disk
except a temporary file that is deleted immediately). After importing, it calls
scripts/wire-credential.py to attach the credential to the right nodes.
"""
import getpass
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
N8N_BIN = os.environ.get("N8N_BIN") or str(Path.home() / ".local/bin/n8n")

CREDENTIALS = {
    "telegram": {
        "type": "telegramApi",
        "name": "ShiftHub Telegram",
        "fields": [
            ("accessToken", "Bot token from @BotFather", True),
        ],
    },
    "smtp": {
        "type": "smtp",
        "name": "ShiftHub Gmail SMTP",
        "fields": [
            ("host", "SMTP host (smtp.gmail.com)", False),
            ("port", "SMTP port (587)", False),
            ("user", "Mailbox user (the From address)", False),
            ("password", "Google App Password", True),
        ],
        "defaults": {"host": "smtp.gmail.com", "port": "587", "secure": False, "disableStartTls": False},
    },
    "imap": {
        "type": "imap",
        "name": "ShiftHub Gmail IMAP",
        "fields": [
            ("host", "IMAP host (imap.gmail.com)", False),
            ("port", "IMAP port (993)", False),
            ("user", "Mailbox user (the From address)", False),
            ("password", "Google App Password", True),
        ],
        "defaults": {"host": "imap.gmail.com", "port": "993", "secure": True},
    },
}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in CREDENTIALS:
        fail("usage: python3 scripts/add-credential.py telegram|smtp|imap")
    spec = CREDENTIALS[sys.argv[1]]

    data = dict(spec.get("defaults", {}))
    print(f"Creating credential: {spec['name']} ({spec['type']})\n")
    for key, prompt, secret in spec["fields"]:
        if secret:
            value = getpass.getpass(f"{prompt}: ")
        else:
            value = input(f"{prompt} [{data.get(key, '')}]: ").strip() or str(data.get(key, ""))
        if not value:
            fail(f"{prompt} is required")
        data[key] = value

    payload = [{"name": spec["name"], "type": spec["type"], "data": data}]
    handle, path = tempfile.mkstemp(suffix=".json", prefix="shifthub-cred-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.chmod(path, 0o600)
        result = subprocess.run(
            [N8N_BIN, "import:credentials", f"--input={path}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            fail(f"n8n import:credentials failed:\n{result.stdout}\n{result.stderr}")
        print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "imported")
    finally:
        Path(path).unlink(missing_ok=True)

    subprocess.run([sys.executable, str(REPO / "scripts" / "wire-credential.py"), spec["type"]], check=True)


if __name__ == "__main__":
    main()
