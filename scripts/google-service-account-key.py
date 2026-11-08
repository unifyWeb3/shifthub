#!/usr/bin/env python3
"""
Turn a Google service-account JSON key into the two values n8n asks for.

Usage:
    python3 scripts/google-service-account-key.py ~/Downloads/my-key.json

Prints the service-account email and copies the private key to the Windows
clipboard (when running under WSL), so you can paste it straight into n8n's
"Google Service Account API" credential. Falls back to printing the key.

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


def main() -> None:
    if len(sys.argv) != 2:
        fail("pass the path to the service-account JSON key, e.g. "
             "python3 scripts/google-service-account-key.py ~/Downloads/my-key.json")

    key_path = Path(sys.argv[1]).expanduser()
    if not key_path.is_file():
        fail(f"file not found: {key_path}")

    try:
        data = json.loads(key_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{key_path} is not valid JSON ({exc})")

    email = str(data.get("client_email") or "").strip()
    private_key = str(data.get("private_key") or "")
    if not email or "iam.gserviceaccount.com" not in email:
        fail("this does not look like a service-account key (no client_email)")
    if "BEGIN PRIVATE KEY" not in private_key or "END PRIVATE KEY" not in private_key:
        fail("this key has no private_key field — download the JSON key from "
             "Google Cloud Console → IAM & Admin → Service Accounts → Keys")

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
