#!/usr/bin/env python3
"""
Copy the workflow JSON files from the repo into the local n8n instance.

The repo files are the source of truth for the workflow *shape* (code,
connections). They deliberately contain no credentials and the placeholder
spreadsheet id, so this script keeps what the instance already knows:

  * the credential of every node with the same node id
  * the node positions (the canvas layout you may have moved in the UI)
  * the real spreadsheet id and the OAuth setting on Google Sheets nodes
  * node notes you added in the UI

Everything else (code, expressions, connections, node set) comes from the repo.

After the copy it writes a new version snapshot and points the published
version at it, because that snapshot - not the draft - is what n8n runs.

Usage:
    python3 scripts/sync-workflows.py [--dry-run] [--only 10-seed-demo-data.json]
"""
import argparse
import json
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO / "n8n" / "workflows"
DB = Path.home() / ".n8n" / "database.sqlite"
SERVICE = "shifthub-n8n"
PLACEHOLDER = "PASTE_GOOGLE_SPREADSHEET_ID"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def service_state() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def service(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=False)


def merge_node(repo_node: dict, live_node: dict | None,
               fallback: dict | None = None) -> tuple[dict, list]:
    """Repo shape + the instance's credentials, layout and sheet id."""
    notes = []
    node = json.loads(json.dumps(repo_node))  # deep copy

    if live_node is None and fallback is None:
        return node, notes

    source = live_node or {}

    # credentials: the instance's own, otherwise a sibling of the same type
    if source.get("credentials"):
        node["credentials"] = source["credentials"]
    elif fallback and fallback.get("credentials"):
        node["credentials"] = fallback["credentials"]
        notes.append("credentials copied")

    if live_node is not None:
        if live_node.get("position"):
            node["position"] = live_node["position"]
        if live_node.get("notes") and not node.get("notes"):
            node["notes"] = live_node["notes"]
        if live_node.get("webhookId") and not node.get("webhookId"):
            node["webhookId"] = live_node["webhookId"]

    if node.get("type") == "n8n-nodes-base.googleSheets":
        candidates = [source, fallback or {}]
        live_doc = None
        for candidate in candidates:
            doc = candidate.get("parameters", {}).get("documentId")
            if (isinstance(doc, dict) and doc.get("value")
                    and doc.get("value") != PLACEHOLDER):
                live_doc = doc
                break
        repo_doc = node.get("parameters", {}).get("documentId")
        if (isinstance(repo_doc, dict) and repo_doc.get("value") == PLACEHOLDER
                and live_doc is not None):
            node["parameters"]["documentId"] = live_doc
            notes.append("sheet id")
        for candidate in candidates:
            auth = candidate.get("parameters", {}).get("authentication")
            if auth:
                node["parameters"]["authentication"] = auth
                break

    # the maintenance workflow holds the live public URL, the repo only has the marker
    if "PASTE_PUBLIC_BASE_URL" in json.dumps(node.get("parameters", {})):
        node["parameters"] = live_node.get("parameters", node["parameters"])
        notes.append("live url")
    return node, notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="sync a single file name from n8n/workflows/")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB}")

    files = sorted(WORKFLOW_DIR.glob("*.json"))
    if args.only:
        files = [f for f in files if f.name == args.only]
        if not files:
            fail(f"no workflow file named {args.only}")

    conn = sqlite3.connect(DB)
    live = dict(conn.execute("select name, id from workflow_entity").fetchall())

    plans = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        workflow_id = live.get(data["name"])
        if not workflow_id:
            print(f"  ! {data['name']}: not in this n8n instance, skipped")
            continue
        row = conn.execute(
            "select nodes, connections, versionCounter from workflow_entity where id = ?",
            (workflow_id,),
        ).fetchone()
        live_nodes = {n.get("id"): n for n in json.loads(row[0])}
        # a template per node type, so a node that only exists in the repo can
        # inherit the credential and the sheet id from its siblings
        templates: dict[str, dict] = {}
        for node in live_nodes.values():
            node_type = node.get("type")
            if not node_type:
                continue
            current = templates.get(node_type)
            if current is None:
                templates[node_type] = node
                continue
            if not current.get("credentials") and node.get("credentials"):
                templates[node_type] = node
        merged = []
        kept = []
        for repo_node in data.get("nodes", []):
            node, notes = merge_node(repo_node, live_nodes.get(repo_node.get("id")),
                                     templates.get(repo_node.get("type")))
            merged.append(node)
            if notes:
                kept.append(f"{node.get('name')}({','.join(notes)})")
        try:
            live_connections = json.loads(row[1] or "{}")
        except json.JSONDecodeError:
            live_connections = {}

        same = (merged == json.loads(row[0])
                and data.get("connections") == live_connections)
        suffix = f"  kept: {', '.join(kept)}" if kept else ""
        print(f"  - {data['name'][:56]:58}{suffix}"
              + ("  (already up to date)" if same else ""))
        if same:
            continue
        plans.append((workflow_id, data["name"], merged, data.get("connections", {}), row[2]))
    conn.close()

    if not plans:
        print("\nnothing to do")
        return

    print()
    was_active = service_state() == "active"
    if was_active and not args.dry_run:
        print("stopping n8n...")
        service("stop")
        time.sleep(2)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    conn = sqlite3.connect(DB)
    try:
        for workflow_id, name, nodes, connections, counter in plans:
            new_version_id = str(uuid.uuid4())
            conn.execute(
                "insert into workflow_history (versionId, workflowId, authors, createdAt, updatedAt, "
                "nodes, connections, name, autosaved, description, nodeGroups) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_version_id, workflow_id, "sync-workflows", now, now,
                 json.dumps(nodes, separators=(",", ":")), json.dumps(connections), None, 0, None, "[]"),
            )
            conn.execute(
                "update workflow_entity set nodes = ?, connections = ?, versionId = ?, "
                "versionCounter = ?, active = 1, activeVersionId = ?, updatedAt = ? where id = ?",
                (json.dumps(nodes, separators=(",", ":")), json.dumps(connections),
                 new_version_id, (counter or 0) + 1, new_version_id, now, workflow_id),
            )
            print(f"  * {name}: synced (published version {new_version_id})")
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


if __name__ == "__main__":
    main()
