#!/usr/bin/env python3
"""
Sync webhook paths from the repo workflow JSONs into the local n8n instance.

n8n 2.x builds the production webhook path as
    /webhook/<workflowId>/<encodeURIComponent(lowercased node name)>/<node path>
when a Webhook node has no `webhookId`. That form contains the workflow id and
breaks as soon as a node name has a space (the incoming path is URL-decoded
before the lookup, so "%20" can never match).

Setting `webhookId` on the node switches n8n to the stable short form
    /webhook/<node path>
which is what the ShiftHub web app and the reminder e-mails already use.

This script copies the `webhookId` property from n8n/workflows/*.json into the
workflow stored in the n8n database (draft + a fresh version snapshot) so that
n8n's publication pipeline re-registers the webhooks with the new paths.
Publish the workflows afterwards (`n8n publish:workflow --id=<id>`).

Usage:
    python3 scripts/sync-webhook-paths.py [--dry-run]
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


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def service_state() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def service(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=False)


def repo_webhook_ids() -> dict:
    """name -> {node id: webhookId} taken from the repo workflow files."""
    wanted = {}
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping = {}
        for node in data.get("nodes", []):
            if node.get("type") != "n8n-nodes-base.webhook":
                continue
            webhook_id = node.get("webhookId")
            if webhook_id:
                mapping[node["id"]] = webhook_id
        if mapping:
            wanted[data["name"]] = mapping
    return wanted


def patch_nodes(nodes_json: str, mapping: dict) -> tuple[str, list]:
    nodes = json.loads(nodes_json)
    changed = []
    for node in nodes:
        wanted = mapping.get(node.get("id"))
        if wanted and node.get("webhookId") != wanted:
            node["webhookId"] = wanted
            changed.append(node.get("name"))
    return json.dumps(nodes, separators=(",", ":")), changed


def needs_work(workflow_id: str, mapping: dict, conn) -> bool:
    row = conn.execute("select nodes from workflow_entity where id = ?", (workflow_id,)).fetchone()
    if not row:
        return False
    _, changed = patch_nodes(row[0], mapping)
    if changed:
        return True
    for (version_nodes,) in conn.execute(
        "select nodes from workflow_history where workflowId = ?", (workflow_id,)
    ).fetchall():
        _, version_changed = patch_nodes(version_nodes, mapping)
        if version_changed:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="create a new version snapshot even when the content already matches "
                             "(needed to make n8n re-register the webhooks)")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB}")

    wanted = repo_webhook_ids()
    if not wanted:
        fail("no webhookId found in the repo workflow files")

    conn = sqlite3.connect(DB)
    live = dict(conn.execute("select name, id from workflow_entity").fetchall())

    plans = []
    for name, mapping in wanted.items():
        workflow_id = live.get(name)
        if not workflow_id:
            print(f"  ! {name}: not in this n8n instance, skipped")
            continue
        if not needs_work(workflow_id, mapping, conn) and not args.force:
            print(f"  - {name}: already up to date")
            continue
        plans.append((workflow_id, name, mapping))
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

    conn = sqlite3.connect(DB)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        for workflow_id, name, mapping in plans:
            row = conn.execute(
                "select nodes, connections, versionCounter from workflow_entity where id = ?",
                (workflow_id,),
            ).fetchone()
            nodes_json, connections_json, version_counter = row
            patched_nodes, changed = patch_nodes(nodes_json, mapping)
            if not changed:
                # draft is fine, only the stored version snapshot is stale
                history = conn.execute(
                    "select nodes, connections, name, autosaved, description, nodeGroups "
                    "from workflow_history where workflowId = ? order by updatedAt desc limit 1",
                    (workflow_id,),
                ).fetchone()
                connections_json = history[1]
                patched_nodes = history[0]
            new_version_id = str(uuid.uuid4())
            conn.execute(
                "update workflow_entity set nodes = ?, versionId = ?, versionCounter = ?, "
                "updatedAt = ? where id = ?",
                (patched_nodes, new_version_id, (version_counter or 0) + 1, now, workflow_id),
            )
            conn.execute(
                "insert into workflow_history (versionId, workflowId, authors, createdAt, updatedAt, "
                "nodes, connections, name, autosaved, description, nodeGroups) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_version_id, workflow_id, "sync-webhook-paths", now, now,
                 patched_nodes, connections_json, None, 0, None, "[]"),
            )
            print(f"  * {name}: webhook paths updated (new version snapshot)")
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

    print("\nnow republish the changed workflows:")
    for workflow_id, name, _mapping in plans:
        print(f"  n8n publish:workflow --id={workflow_id}   # {name}")


if __name__ == "__main__":
    main()
