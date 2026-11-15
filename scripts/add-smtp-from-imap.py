#!/usr/bin/env python3
"""
Create the ShiftHub Gmail SMTP credential from the App Password that is already
stored in the n8n IMAP credential (same mailbox, same Google App Password).

Why this exists:
    A Google App Password works for BOTH imap.gmail.com:993 and
    smtp.gmail.com:587. The user already provided it once (for the IMAP
    credential), so there is no reason to ask for it again or to type it into
    a terminal.

    The App Password is read from the encrypted credential in the local n8n
    database, used in memory only, and never printed or written to disk.
    The imported credential is encrypted by n8n itself.

Usage:
    python3 scripts/add-smtp-from-imap.py [--dry-run]
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

N8N_DIR = Path.home() / ".n8n"
DB = N8N_DIR / "database.sqlite"
N8N_BIN = os.environ.get("N8N_BIN") or str(Path.home() / ".local/bin/n8n")
REPO = Path(__file__).resolve().parent.parent

CREDENTIAL_NAME = "ShiftHub Gmail SMTP"
IMAP_NAME = "ShiftHub Gmail IMAP"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def decrypt_legacy(blob: str, key: str) -> dict:
    """Decrypt a legacy n8n credential (Salted__ + aes-256-cbc)."""
    import base64
    import hashlib

    raw = base64.b64decode(blob)
    if raw[:8] != b"Salted__":
        fail("the stored IMAP credential is not in the expected encrypted format")
    salt, data = raw[8:16], raw[16:]
    # OpenSSL's EVP_BytesToKey: MD5(prev || password_bytes || salt), repeated.
    # The instance key is ASCII, so latin-1 and UTF-8 give the same bytes.
    material, prev = b"", b""
    while len(material) < 48:
        h = hashlib.md5(prev + key.encode("latin-1") + salt).digest()
        material += h
        prev = h
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        fail("the python 'cryptography' package is needed to read the IMAP credential")
    cipher = Cipher(algorithms.AES(material[:32]), modes.CBC(material[32:48]))
    decryptor = cipher.decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    pad = plain[-1]
    return json.loads(plain[:-pad].decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would happen without changing anything")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB}")

    config = json.loads((N8N_DIR / "config").read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select id, name, data from credentials_entity where type = 'imap' and name = ?",
        (IMAP_NAME,),
    ).fetchone()
    conn.close()
    if not row:
        fail(f"no IMAP credential named {IMAP_NAME!r} - create it first")

    imap = decrypt_legacy(row[2], config["encryptionKey"])
    user = str(imap.get("user") or "").strip()
    password = str(imap.get("password") or "").strip()
    if not user or not password:
        fail("the stored IMAP credential has no user/password")

    print(f"source credential : {row[1]} ({row[0]})")
    print(f"mailbox           : {user}")
    print(f"app password      : present ({len(password)} chars, not shown)")

    payload = [{
        "name": CREDENTIAL_NAME,
        "type": "smtp",
        "data": {
            "host": "smtp.gmail.com",
            "port": "587",
            "user": user,
            "password": password,
            "secure": False,
            "disableStartTls": False,
        },
    }]

    if args.dry_run:
        print("[dry run] would create the SMTP credential and wire it to every email node")
        return

    # Reuse an existing SMTP credential instead of creating a second one with
    # the same secret (n8n's import always makes a new id).
    conn = sqlite3.connect(DB)
    existing = conn.execute(
        "select id, name, data from credentials_entity where type = 'smtp'",
    ).fetchall()
    conn.close()
    reusable = None
    for cred_id, cred_name, blob in existing:
        try:
            stored = decrypt_legacy(blob, config["encryptionKey"])
        except Exception:
            continue
        if (str(stored.get("host")) == "smtp.gmail.com"
                and str(stored.get("user")) == user
                and str(stored.get("password")) == password):
            reusable = (cred_id, cred_name)
            break

    if reusable:
        print(f"reusing the existing SMTP credential: {reusable[1]} ({reusable[0]})")
    else:
        handle, path = tempfile.mkstemp(suffix=".json", prefix="shifthub-smtp-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.chmod(path, 0o600)
            result = subprocess.run([N8N_BIN, "import:credentials", f"--input={path}"],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                fail(f"n8n import:credentials failed:\n{result.stdout}\n{result.stderr}")
            print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "imported")
        finally:
            Path(path).unlink(missing_ok=True)

    subprocess.run([sys.executable, str(REPO / "scripts" / "wire-credential.py"), "smtp"],
                   check=True)
    print("\nre-publishing the drafts so the running workflows carry the credential:")
    subprocess.run([sys.executable, str(REPO / "scripts" / "publish-drafts.py")], check=True)


if __name__ == "__main__":
    main()
