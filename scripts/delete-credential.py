#!/usr/bin/env python3
"""
Delete an n8n credential that is not referenced by any workflow node.

Usage:
    python3 scripts/delete-credential.py <credential-id>

Safety:
    - refuses to delete a credential that is still referenced by a node
    - removes the shared/project link too, so no orphan rows are left behind
    - n8n must be stopped while the database is edited
"""
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

N8N_DIR = Path.home() / ".n8n"
DB = N8N_DIR / "database.sqlite"
SERVICE = "shifthub-n8n"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def service_state() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: delete-credential.py <credential-id>")
    cred_id = sys.argv[1].strip()

    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select id, name, type from credentials_entity where id = ?", (cred_id,)
    ).fetchone()
    if not row:
        fail(f"no credential with id {cred_id!r}")

    references = []
    for wf_id, wf_name, nodes_json in conn.execute("select id, name, nodes from workflow_entity"):
        try:
            nodes = json.loads(nodes_json)
        except json.JSONDecodeError:
            continue
        for node in nodes:
            for cred_type, ref in (node.get("credentials") or {}).items():
                if isinstance(ref, dict) and ref.get("id") == cred_id:
                    references.append(f"{wf_name} / {node.get('name')}")
    conn.close()

    if references:
        fail(f"credential is still used by: {'; '.join(references)}")

    was_active = service_state() == "active"
    if was_active:
        print("stopping n8n...")
        subprocess.run(["systemctl", "--user", "stop", SERVICE], check=False)
        time.sleep(2)

    conn = sqlite3.connect(DB)
    try:
        conn.execute("delete from shared_credentials where credentialsId = ?", (cred_id,))
        conn.execute("delete from credential_dependency where credentialId = ?", (cred_id,))
        conn.execute("delete from credentials_entity where id = ?", (cred_id,))
        conn.commit()
    finally:
        conn.close()

    if was_active:
        print("starting n8n...")
        subprocess.run(["systemctl", "--user", "start", SERVICE], check=False)
        for _ in range(30):
            time.sleep(2)
            if service_state() == "active":
                break
        print(f"n8n is {service_state()}")

    print(f"deleted credential: {row[1]} ({row[2]}, {row[0]})")


if __name__ == "__main__":
    main()
