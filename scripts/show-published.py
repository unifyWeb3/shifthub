#!/usr/bin/env python3
"""
Show what the PUBLISHED version of a workflow actually contains.

n8n runs the published snapshot (workflow_history), not the draft
(workflow_entity). This script prints the published nodes, their credentials
and the connections, so we can prove the running workflow has the wiring we
think it has.

Usage:
    python3 scripts/show-published.py <workflow-id>
"""
import json
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".n8n" / "database.sqlite"


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: show-published.py <workflow-id>", file=sys.stderr)
        raise SystemExit(1)
    workflow_id = sys.argv[1].strip()

    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select versionId, name, createdAt, nodes, connections from workflow_history "
        "where workflowId = ? order by createdAt desc limit 1",
        (workflow_id,),
    ).fetchone()
    conn.close()
    if not row:
        print(f"no published version for workflow {workflow_id}", file=sys.stderr)
        raise SystemExit(1)

    version_id, name, created_at, nodes_json, connections_json = row
    nodes = json.loads(nodes_json)
    connections = json.loads(connections_json)

    print(f"workflow : {name}")
    print(f"id       : {workflow_id}")
    print(f"version  : {version_id}")
    print(f"published: {created_at}")
    print("\nnodes:")
    for node in nodes:
        creds = node.get("credentials") or {}
        cred_text = ", ".join(
            f"{ctype}={ref.get('id')}" for ctype, ref in creds.items()
            if isinstance(ref, dict) and ref.get("id")
        ) or "NO CREDENTIAL"
        print(f"  - {node['name']:34} {node['type'].split('.')[-1]:16} {cred_text}")
    print("\nconnections:")
    for source, outputs in connections.items():
        targets = [
            target["node"]
            for output in outputs.get("main", [])
            for target in output
            if isinstance(target, dict)
        ]
        print(f"  {source} -> {', '.join(targets) if targets else '(end)'}")


if __name__ == "__main__":
    main()
