#!/usr/bin/env python3
"""
Publish the current draft of every ShiftHub workflow in the local n8n instance.

Why this exists
---------------
n8n runs the *published* version of a workflow (a snapshot in the
`workflow_history` table), not the draft in `workflow_entity`. The snapshots
that came from `n8n import:workflow` were taken before the Google credential
and the spreadsheet id were wired in, so those published workflows ran without
credentials. This script copies the current draft (credentials + spreadsheet id
included) into a fresh version snapshot and points the active version at it,
which is exactly what `n8n publish:workflow` does - but for every workflow in
one pass instead of one CLI start per workflow.

The running n8n instance notices the version skew within seconds (its
publication reconciler runs every 10s) and re-registers the triggers.

Usage:
    python3 scripts/publish-drafts.py [--dry-run]
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DB.is_file():
        fail(f"no n8n database at {DB}")

    conn = sqlite3.connect(DB)
    workflows = conn.execute(
        "select id, name, nodes, connections, versionCounter, active, activeVersionId "
        "from workflow_entity order by name"
    ).fetchall()
    if not workflows:
        fail("no workflows in the n8n database")

    print(f"{len(workflows)} workflow(s) found\n")
    for workflow_id, name, nodes, connections, counter, active, active_version in workflows:
        node_list = json.loads(nodes)
        sheets = [n for n in node_list if n.get("type") == "n8n-nodes-base.googleSheets"]
        missing = [n.get("name") for n in sheets if not n.get("credentials")]
        flag = f"  !! {len(missing)} sheet node(s) without credentials: {missing}" if missing else ""
        print(f"  - {name[:58]:60} active={bool(active)} versionCounter={counter}{flag}")

    if args.dry_run:
        print("\n[dry run] no changes written")
        return

    print()
    was_active = service_state() == "active"
    if was_active:
        print("stopping n8n...")
        service("stop")
        time.sleep(2)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        for workflow_id, name, nodes, connections, counter, active, active_version in workflows:
            new_version_id = str(uuid.uuid4())
            conn.execute(
                "insert into workflow_history (versionId, workflowId, authors, createdAt, updatedAt, "
                "nodes, connections, name, autosaved, description, nodeGroups) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_version_id, workflow_id, "publish-drafts", now, now,
                 nodes, connections, None, 0, None, "[]"),
            )
            conn.execute(
                "update workflow_entity set versionId = ?, versionCounter = ?, active = 1, "
                "activeVersionId = ?, updatedAt = ? where id = ?",
                (new_version_id, (counter or 0) + 1, new_version_id, now, workflow_id),
            )
            print(f"  * {name}: new published version {new_version_id}")
        conn.commit()
    finally:
        conn.close()
        if was_active:
            print("starting n8n...")
            service("start")
            for _ in range(30):
                time.sleep(2)
                if service_state() == "active":
                    break
            print(f"n8n is {service_state()}")

    print("\nn8n re-publishes the workflows within ~15 seconds "
          "(publication reconciler, every 10s). Check with:")
    print("  sqlite3 ~/.n8n/database.sqlite \\")
    print("    'select workflowId, publishedVersionId from workflow_published_version;'")


if __name__ == "__main__":
    main()
