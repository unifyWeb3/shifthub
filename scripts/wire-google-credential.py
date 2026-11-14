#!/usr/bin/env python3
"""
Wire the Google Sheets credential + spreadsheet ID into every ShiftHub workflow
in the local n8n instance.

Usage:
    python3 scripts/wire-google-credential.py <SPREADSHEET_ID> [CREDENTIAL_NAME]
    python3 scripts/wire-google-credential.py <SPREADSHEET_ID> --dry-run

The spreadsheet ID is the part of the sheet URL between /d/ and /edit:
    https://docs.google.com/spreadsheets/d/1AbC...xYz/edit
                                  ^^^^^^^^^ this ^^^^^^^^^

CREDENTIAL_NAME defaults to the only Google Sheets OAuth2 credential in the
instance (it is usually called "Google Sheets account 2").

The script stops n8n, rewrites the stored workflow nodes, and starts n8n again.
It never prints the credential ID/secret, only names.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

N8N_DIR = Path.home() / ".n8n"
DB = N8N_DIR / "database.sqlite"
SERVICE = "shifthub-n8n"
SHEETS_NODE = "n8n-nodes-base.googleSheets"
PLACEHOLDER = "PASTE_GOOGLE_SPREADSHEET_ID"
CRED_TYPE = "googleSheetsOAuth2Api"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def service_state() -> str:
    result = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "unknown"


def service(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=False)


def find_credentials(conn):
    return conn.execute(
        "select id, name, type from credentials_entity where type = ?", (CRED_TYPE,)
    ).fetchall()


def wire(sheet_id: str, cred_id: str, cred_name: str, dry_run: bool) -> int:
    conn = sqlite3.connect(DB)
    changed = 0
    replaced = 0
    rows = conn.execute("select id, name, nodes from workflow_entity").fetchall()
    for wf_id, wf_name, nodes_json in rows:
        try:
            nodes = json.loads(nodes_json)
        except json.JSONDecodeError:
            print(f"  ! {wf_name}: node JSON unreadable, skipped")
            continue
        touched = False
        for node in nodes:
            if node.get("type") != SHEETS_NODE:
                continue
            params = node.setdefault("parameters", {})
            if params.get("authentication") != "oAuth2":
                params["authentication"] = "oAuth2"
                touched = True
            doc = params.get("documentId")
            if isinstance(doc, dict) and doc.get("value") == PLACEHOLDER:
                doc["value"] = sheet_id
                replaced += 1
                touched = True
            node["credentials"] = {CRED_TYPE: {"id": cred_id, "name": cred_name}}
            touched = True
        if touched:
            changed += 1
            if not dry_run:
                conn.execute(
                    "update workflow_entity set nodes = ?, updatedAt = ? where id = ?",
                    (json.dumps(nodes, separators=(",", ":")), "CURRENT_TIMESTAMP", wf_id),
                )
        print(f"  - {wf_name}")
    if not dry_run:
        conn.commit()
    conn.close()
    print(f"\n{'[dry run] would update' if dry_run else 'updated'} {changed} workflow(s), "
          f"{replaced} placeholder(s) replaced")
    return replaced


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("spreadsheet_id")
    parser.add_argument("credential_name", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB} — is n8n installed for this user?")

    conn = sqlite3.connect(DB)
    creds = find_credentials(conn)
    conn.close()
    if not creds:
        fail(f"no {CRED_TYPE} credential found in n8n — create it in the UI first")
    if args.credential_name:
        matches = [c for c in creds if c[1] == args.credential_name]
        if not matches:
            names = ", ".join(c[1] for c in creds)
            fail(f"credential {args.credential_name!r} not found (have: {names})")
        cred = matches[0]
    elif len(creds) == 1:
        cred = creds[0]
    else:
        names = ", ".join(c[1] for c in creds)
        fail(f"several Google credentials exist ({names}) — pass the one to use")

    print(f"credential: {cred[1]} ({cred[0]})")
    print(f"spreadsheet: {args.spreadsheet_id}\n")

    was_active = service_state() == "active"
    if was_active and not args.dry_run:
        print("stopping n8n...")
        service("stop")
        time.sleep(2)

    try:
        wire(args.spreadsheet_id, cred[0], cred[1], args.dry_run)
    finally:
        if was_active and not args.dry_run:
            print("starting n8n...")
            service("start")
            for _ in range(30):
                time.sleep(2)
                if service_state() == "active":
                    break
            print(f"n8n is {service_state()}")


if __name__ == "__main__":
    main()
