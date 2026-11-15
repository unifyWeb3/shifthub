#!/usr/bin/env python3
"""
Read the rota sheet directly through the Google Sheets API.

Why this exists:
    The rota sheet is the source of truth for the reminder/escalation stamps,
    but the only credential that can read it lives encrypted inside the local
    n8n instance. This script decrypts that credential, refreshes the OAuth
    access token and reads the sheet - so you can verify a stamp landed
    without opening the browser.

    Tokens are used in memory only. Nothing is printed, written to disk or
    sent anywhere except Google's own endpoints.

Usage:
    python3 scripts/read-rota.py
    python3 scripts/read-rota.py --tab Rota
    python3 scripts/read-rota.py --only SHIFT-DEMO-01
    python3 scripts/read-rota.py --json
"""
import argparse
import base64
import hashlib
import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

N8N_DIR = Path.home() / ".n8n"
DB = N8N_DIR / "database.sqlite"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{tab}"

DEFAULT_SHEET_ID = "1eHo1kIBUcAnAwP-joLm6RFe7cpcD6wz18FJtHIZfzRw"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def decrypt_legacy(blob: str, key: str) -> dict:
    """Decrypt a legacy n8n credential (Salted__ + aes-256-cbc)."""
    raw = base64.b64decode(blob)
    if raw[:8] != b"Salted__":
        fail("the stored credential is not in the expected encrypted format")
    salt, data = raw[8:16], raw[16:]
    material, prev = b"", b""
    while len(material) < 48:
        h = hashlib.md5(prev + key.encode("latin-1") + salt).digest()
        material += h
        prev = h
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        fail("the python 'cryptography' package is needed to read the credential")
    decryptor = Cipher(algorithms.AES(material[:32]), modes.CBC(material[32:48])).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    return json.loads(plain[:-plain[-1]].decode("utf-8"))


def google_credential() -> dict:
    config = json.loads((N8N_DIR / "config").read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select data from credentials_entity where type = 'googleSheetsOAuth2Api' limit 1"
    ).fetchone()
    conn.close()
    if not row:
        fail("no googleSheetsOAuth2Api credential in the local n8n instance")
    return decrypt_legacy(row[0], config["encryptionKey"])


def access_token(credential: dict) -> str:
    token_data = credential.get("oauthTokenData") or {}
    refresh = token_data.get("refresh_token")
    if not refresh:
        fail("the Google credential has no refresh token - sign in with Google again in n8n")
    payload = urllib.parse.urlencode({
        "client_id": credential["clientId"],
        "client_secret": credential["clientSecret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    request = urllib.request.Request(TOKEN_URL, data=payload,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        fail(f"Google rejected the token refresh: {error.read().decode()[:300]}")
    token = body.get("access_token")
    if not token:
        fail("Google did not return an access token")
    return token


def read_tab(token: str, sheet_id: str, tab: str) -> list[dict]:
    url = SHEETS_URL.format(id=sheet_id, tab=urllib.parse.quote(tab))
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        fail(f"could not read the {tab!r} tab: {error.read().decode()[:300]}")
    values = body.get("values") or []
    if not values:
        return []
    headers = values[0]
    return [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in values[1:]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tab", default="Rota", help="tab to read (default: Rota)")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--only", help="only print rows containing this text")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args()

    token = access_token(google_credential())
    rows = read_tab(token, args.sheet_id, args.tab)

    if args.only:
        rows = [r for r in rows if args.only in json.dumps(r)]

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    print(f"tab '{args.tab}': {len(rows)} row(s)")
    for row in rows:
        print(f"  {row.get('shiftId',''):16} {row.get('staffName',''):18} "
              f"status={row.get('status',''):9} "
              f"1d='{row.get('reminder1dSent','')}' "
              f"2h='{row.get('reminder2hSent','')}' "
              f"3h='{row.get('escalation3hSent','')}'")


if __name__ == "__main__":
    main()
