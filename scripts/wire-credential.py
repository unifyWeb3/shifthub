#!/usr/bin/env python3
"""
Attach an existing n8n credential to every node of the matching type in all
ShiftHub workflows (and optionally replace the spreadsheet placeholder).

Usage:
    python3 scripts/wire-credential.py <credential-type> [name-or-id] [--spreadsheet-id ID] [--dry-run]

Credential types and the nodes they get attached to:

    googleSheetsOAuth2Api  ->  Google Sheets nodes
    googleApi              ->  Google Sheets nodes (service account)
    telegramApi            ->  Telegram + Telegram Trigger nodes
    smtp                   ->  Send Email nodes
    imap                   ->  Inbox Trigger (IMAP) nodes

If several credentials of that type exist, pass the name or the id to pick one.

The script stops n8n, rewrites the stored workflow nodes, and starts n8n again.
It never prints credential secrets, only names and ids.
"""
import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

N8N_DIR = Path.home() / ".n8n"
DB = N8N_DIR / "database.sqlite"
SERVICE = "shifthub-n8n"
PLACEHOLDER = "PASTE_GOOGLE_SPREADSHEET_ID"

CREDENTIAL_NODE_TYPES = {
    "googleSheetsOAuth2Api": ["n8n-nodes-base.googleSheets"],
    "googleApi": ["n8n-nodes-base.googleSheets"],
    "telegramApi": ["n8n-nodes-base.telegram", "n8n-nodes-base.telegramTrigger"],
    "smtp": ["n8n-nodes-base.emailSend"],
    "imap": ["n8n-nodes-base.emailReadImap"],
}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def service_state() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def service(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("credential_type", choices=sorted(CREDENTIAL_NODE_TYPES))
    parser.add_argument("credential", nargs="?", help="credential name or id")
    parser.add_argument("--spreadsheet-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB} — is n8n installed for this user?")

    conn = sqlite3.connect(DB)
    creds = conn.execute(
        "select id, name, type from credentials_entity where type = ?",
        (args.credential_type,),
    ).fetchall()
    if not creds:
        fail(f"no {args.credential_type} credential in n8n — create it in the UI first")
    if args.credential:
        matches = [c for c in creds if c[1] == args.credential or c[0] == args.credential]
        if not matches:
            names = ", ".join(f"{c[1]} ({c[0]})" for c in creds)
            fail(f"credential {args.credential!r} not found (have: {names})")
        if len(matches) > 1:
            fail("several credentials match — pass the credential id: "
                 + ", ".join(c[0] for c in matches))
        cred = matches[0]
    elif len(creds) == 1:
        cred = creds[0]
    else:
        names = ", ".join(f"{c[1]} ({c[0]})" for c in creds)
        fail(f"several {args.credential_type} credentials exist ({names}) — pass the one to use")

    node_types = CREDENTIAL_NODE_TYPES[args.credential_type]
    print(f"credential : {cred[1]} ({cred[0]})")
    print(f"node types : {', '.join(node_types)}")
    if args.spreadsheet_id:
        print(f"spreadsheet: {args.spreadsheet_id}")
    print()

    was_active = service_state() == "active"
    if was_active and not args.dry_run:
        print("stopping n8n...")
        service("stop")
        time.sleep(2)

    conn = sqlite3.connect(DB)
    touched_workflows = 0
    touched_nodes = 0
    placeholders = 0
    try:
        for wf_id, wf_name, nodes_json in conn.execute(
            "select id, name, nodes from workflow_entity"
        ):
            try:
                nodes = json.loads(nodes_json)
            except json.JSONDecodeError:
                print(f"  ! {wf_name}: unreadable node JSON, skipped")
                continue
            changed = False
            for node in nodes:
                if node.get("type") not in node_types:
                    continue
                params = node.setdefault("parameters", {})
                if args.credential_type in ("googleSheetsOAuth2Api", "googleApi"):
                    params["authentication"] = (
                        "oAuth2" if args.credential_type == "googleSheetsOAuth2Api" else "serviceAccount"
                    )
                    if args.spreadsheet_id:
                        doc = params.get("documentId")
                        if isinstance(doc, dict) and doc.get("value") == PLACEHOLDER:
                            doc["value"] = args.spreadsheet_id
                            placeholders += 1
                node["credentials"] = {args.credential_type: {"id": cred[0], "name": cred[1]}}
                touched_nodes += 1
                changed = True
            if changed:
                touched_workflows += 1
                if not args.dry_run:
                    conn.execute(
                        "update workflow_entity set nodes = ?, updatedAt = ? where id = ?",
                        (json.dumps(nodes, separators=(",", ":")), "CURRENT_TIMESTAMP", wf_id),
                    )
                print(f"  - {wf_name}")
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()
        if was_active and not args.dry_run:
            print("starting n8n...")
            service("start")
            for _ in range(30):
                time.sleep(2)
                if service_state() == "active":
                    break
            print(f"n8n is {service_state()}")

    print(f"\n{'[dry run] would update' if args.dry_run else 'updated'} "
          f"{touched_workflows} workflow(s), {touched_nodes} node(s), "
          f"{placeholders} spreadsheet placeholder(s)")


if __name__ == "__main__":
    main()
