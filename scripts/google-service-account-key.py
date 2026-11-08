#!/usr/bin/env python3
"""
Turn a Google service-account JSON key into the two values n8n asks for.

Usage:
    python3 scripts/google-service-account-key.py [path-to-key.json]

With no path it looks for the newest service-account JSON in your Windows
Downloads folder (and ~/Downloads). It prints the service-account email and
copies the private key to the Windows clipboard, so you can paste it straight
into n8n's "Google Service Account API" credential. Falls back to printing it.

The JSON key is a secret: never commit it or email it to anyone.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_key(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    email = str(data.get("client_email") or "").strip()
    private_key = str(data.get("private_key") or "")
    if data.get("type") != "service_account":
        return None
    if "iam.gserviceaccount.com" not in email or "BEGIN PRIVATE KEY" not in private_key:
        return None
    return email, private_key


def find_newest_key():
    candidates = [Path.home() / "Downloads"]
    candidates.extend(Path("/mnt/c/Users").glob("*/Downloads"))
    found = []
    for folder in candidates:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            loaded = load_key(path)
            if loaded:
                found.append((path.stat().st_mtime, path, loaded))
    if not found:
        return None
    found.sort(reverse=True)
    _, path, (email, private_key) = found[0]
    print(f"Using the newest service-account key: {path}\n")
    return email, private_key


def main() -> None:
    if len(sys.argv) > 2:
        fail("pass at most one path, e.g. "
             "python3 scripts/google-service-account-key.py ~/Downloads/my-key.json")

    if len(sys.argv) == 2:
        key_path = Path(sys.argv[1]).expanduser()
        if not key_path.is_file():
            fail(f"file not found: {key_path}")
        loaded = load_key(key_path)
        if not loaded:
            fail(f"{key_path} is not a Google service-account JSON key")
        email, private_key = loaded
    else:
        loaded = find_newest_key()
        if not loaded:
            fail("no service-account JSON found. Download the key from Google Cloud "
                 "Console → IAM & Admin → Service Accounts → Keys, then run this again.")
        email, private_key = loaded

    print("\nService Account Email (paste into n8n):\n")
    print(f"  {email}\n")

    clip = shutil.which("clip.exe")
    if clip:
        subprocess.run([clip], input=private_key.encode("utf-16le"), check=True)
        print("Private Key: copied to the Windows clipboard.")
        print("Paste it into n8n's Private Key field (Ctrl+V).\n")
    else:
        print("Private Key (copy everything between the BEGIN and END lines):\n")
        print(private_key)
        print()

    print("Reminder: share the Google Sheet with this email as Editor, "
          "otherwise n8n cannot read or write it.")


if __name__ == "__main__":
    main()
