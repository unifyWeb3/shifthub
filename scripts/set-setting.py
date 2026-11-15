#!/usr/bin/env python3
"""
Write one key/value pair into the `Settings` tab of the ShiftHub spreadsheet.

n8n code and expression nodes cannot read environment variables, so the public
URL (and any other setting that has to follow the machine) is stored in the
spreadsheet. This script patches the maintenance workflow
"ShiftHub — 13 · Maintenance: Set Public Base URL" so it writes the requested
key instead of `publicBaseUrl`, then runs that workflow.

Usage:
    python3 scripts/set-setting.py staffTelegramDefaultChatId 5060676408
    python3 scripts/set-setting.py publicBaseUrl https://example.trycloudflare.com
    python3 scripts/set-setting.py --list
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

DB = Path.home() / ".n8n" / "database.sqlite"
N8N_BIN = os.environ.get("N8N_BIN") or str(Path.home() / ".local/bin/n8n")
MAINTENANCE_WORKFLOW = "ShiftHub — 13 · Maintenance: Set Public Base URL"
SERVICE = "shifthub-n8n"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_workflow(conn):
    row = conn.execute(
        "select id, nodes from workflow_entity where name = ?", (MAINTENANCE_WORKFLOW,)
    ).fetchone()
    if not row:
        fail(f"workflow '{MAINTENANCE_WORKFLOW}' is not in this n8n instance")
    return row


def patch_workflow(conn, workflow_id: str, key: str, value: str) -> None:
    for table, id_column in (("workflow_entity", "id"), ("workflow_history", "versionId")):
        if table == "workflow_entity":
            rows = conn.execute("select id, nodes from workflow_entity where id = ?",
                                (workflow_id,)).fetchall()
        else:
            rows = conn.execute(
                "select versionId, nodes from workflow_history where workflowId = ?",
                (workflow_id,)).fetchall()
        for row_id, nodes_json in rows:
            nodes = json.loads(nodes_json)
            changed = False
            for node in nodes:
                if node.get("type") != "n8n-nodes-base.googleSheets":
                    continue
                columns = node.setdefault("parameters", {}).setdefault("columns", {})
                columns["mappingMode"] = "defineBelow"
                columns["value"] = {"key": key, "value": value}
                columns["matchingColumns"] = ["key"]
                changed = True
            if changed:
                conn.execute(
                    f"update {table} set nodes = ?, updatedAt = CURRENT_TIMESTAMP "
                    f"where {id_column} = ?",
                    (json.dumps(nodes, separators=(",", ":")), row_id),
                )


def run_workflow(workflow_id: str) -> bool:
    env = dict(os.environ)
    # the running instance owns port 5679, so the CLI needs its own broker port
    env["N8N_RUNNERS_BROKER_PORT"] = "5681"
    result = subprocess.run([N8N_BIN, "execute", "--id", workflow_id],
                            capture_output=True, text=True, env=env)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print(output[-1500:])
        return False
    try:
        start = output.find("{\n")
        data = json.loads(output[start:])
    except (ValueError, TypeError):
        print(output[-1500:])
        return False
    if data.get("status") != "success":
        print(json.dumps(data)[:1500])
        return False
    run_data = data.get("data", {}).get("resultData", {}).get("runData", {})
    for name, runs in run_data.items():
        for run in runs:
            if run.get("error"):
                print(f"  ! {name}: {run['error'].get('message')}")
                return False
            rows = run.get("data", {}).get("main", [[]])[0] if run.get("data") else []
            for row in rows[:3]:
                payload = row.get("json", {})
                if payload.get("key"):
                    print(f"  Settings.{payload.get('key')} = {payload.get('value')}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--list", action="store_true",
                        help="print the current Settings rows")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB}")

    conn = sqlite3.connect(DB)
    workflow_id, _nodes = find_workflow(conn)

    if args.list:
        print("read them with the n8n dashboard workflow or open the sheet directly")
        conn.close()
        return

    if not args.key or args.value is None:
        fail("usage: python3 scripts/set-setting.py <key> <value>")
    if not args.value:
        fail("value must not be empty")

    patch_workflow(conn, workflow_id, args.key, args.value)
    conn.commit()
    conn.close()

    print(f"setting {args.key} = {args.value}")
    if not run_workflow(workflow_id):
        fail("the maintenance workflow did not finish successfully")


if __name__ == "__main__":
    main()
