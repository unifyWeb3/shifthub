#!/usr/bin/env python3
"""
Show what the local ShiftHub n8n instance is actually running.

Answers, for every workflow:
  * is it published (active) and does the published version match the draft?
  * did every trigger activate? (a Telegram/IMAP trigger without a credential
    fails here with "Node does not have any credentials set")
  * which public webhook paths are registered?
  * which cron jobs are scheduled and when do they next run?

Usage:
    python3 scripts/check-status.py
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB = Path.home() / ".n8n" / "database.sqlite"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not DB.is_file():
        fail(f"no n8n database at {DB}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    workflows = conn.execute(
        "select id, name, active, activeVersionId, versionId from workflow_entity order by name"
    ).fetchall()
    if not workflows:
        fail("no workflows in the n8n database")

    published = {
        row["workflowId"]: row["publishedVersionId"]
        for row in conn.execute("select workflowId, publishedVersionId from workflow_published_version")
    }
    triggers = {}
    for row in conn.execute(
        "select workflowId, nodeId, status, errorMessage, triggerKind, updatedAt "
        "from workflow_publication_trigger_status"
    ):
        triggers.setdefault(row["workflowId"], []).append(row)

    webhooks = {}
    for row in conn.execute("select workflowId, webhookPath, method from webhook_entity"):
        webhooks.setdefault(row["workflowId"], []).append(row)

    print(f"{'workflow':52} {'published':10} triggers")
    print("-" * 110)
    problems = 0
    for wf in workflows:
        wf_id = wf["id"]
        active = bool(wf["active"]) and wf["activeVersionId"] is not None
        in_sync = published.get(wf_id) == wf["activeVersionId"]
        state = "yes" if active else "no"
        if active and not in_sync:
            state = "stale"
        rows = triggers.get(wf_id, [])
        bad = [r for r in rows if r["status"] not in ("activated",)]
        if bad:
            problems += 1
        summary = ", ".join(
            f"{r['nodeId'][:8]}:{r['status']}"
            + (f" ({r['errorMessage']})" if r["errorMessage"] else "")
            for r in rows
        ) or "-"
        print(f"{wf['name'][:50]:52} {state:10} {summary[:200]}")
        for row in webhooks.get(wf_id, []):
            print(f"{'':52} {'':10}   webhook: {row['method']} /webhook/{row['webhookPath']}")

    print("\ncron jobs (times are UTC in the database; n8n runs them in Africa/Lagos)")
    for row in conn.execute(
        "select id, cronExpression, timezone, enabled, nextRunAt, lastFiredAt, orphanedAt "
        "from scheduled_job order by id"
    ):
        payload = conn.execute(
            "select payload from scheduled_job where id = ?", (row["id"],)
        ).fetchone()[0]
        workflow_id = json.loads(payload).get("workflowId", "?")
        name = conn.execute(
            "select name from workflow_entity where id = ?", (workflow_id,)
        ).fetchone()
        label = (name[0] if name else workflow_id)[:44]
        flag = "" if row["enabled"] and not row["orphanedAt"] else "  <-- disabled/orphaned"
        print(f"  {label:46} {row['cronExpression']:16} next={row['nextRunAt']} "
              f"last={row['lastFiredAt']}{flag}")

    now = datetime.now(timezone.utc)
    print(f"\nnow (UTC): {now:%Y-%m-%d %H:%M:%S}")
    if problems:
        print(f"{problems} workflow(s) have a trigger that failed to activate - "
              f"the message above says why (usually a missing credential).")
    else:
        print("all triggers activated")


if __name__ == "__main__":
    main()
