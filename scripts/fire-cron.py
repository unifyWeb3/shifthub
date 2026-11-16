#!/usr/bin/env python3
"""
Fire a workflow's cron trigger right now, without waiting for its schedule.

n8n's CLI (`n8n execute --id`) can only start a workflow from a Manual or
Execute-Workflow trigger, so it cannot run the cron-triggered workflows
(01, 02, 03, 08, 09). This script instead moves the scheduled job's next run
time to the current minute, so the real scheduler fires the **published**
version of the workflow exactly the way production does.

Usage:
    python3 scripts/fire-cron.py 08              # by workflow number prefix
    python3 scripts/fire-cron.py 08 --wait 120   # wait up to 2 minutes for it to run
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DB = Path.home() / ".n8n" / "database.sqlite"


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_workflow(prefix: str) -> tuple[str, str]:
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select id, name from workflow_entity where name like ? order by name",
        (f"%{prefix}%",),
    ).fetchone()
    conn.close()
    if not row:
        fail(f"no workflow matching {prefix!r}")
    return row[0], row[1]


def jobs_for(conn: sqlite3.Connection, workflow_id: str) -> list[dict]:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(scheduled_job)")]
    found = []
    for raw in conn.execute("select * from scheduled_job"):
        job = dict(zip(cols, raw))
        try:
            payload = json.loads(job.get("payload") or "{}")
        except json.JSONDecodeError:
            continue
        if payload.get("workflowId") == workflow_id:
            found.append(job)
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", help="workflow number or name fragment")
    parser.add_argument("--wait", type=int, default=0,
                        help="seconds to wait for the execution to appear")
    args = parser.parse_args()

    workflow_id, workflow_name = find_workflow(args.workflow)
    print(f"workflow: {workflow_name} ({workflow_id})")

    conn = sqlite3.connect(DB)
    jobs = jobs_for(conn, workflow_id)
    if not jobs:
        fail("this workflow has no scheduled job - it is not cron-triggered")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")
    for job in jobs:
        print(f"  job {job['id']}: cron='{job.get('cronExpression')}' "
              f"next={job.get('nextRunAt')} -> moving to {now}")
        conn.execute("update scheduled_job set nextRunAt = ?, fireAt = ? where id = ?",
                     (now, now, job["id"]))
    conn.commit()
    conn.close()

    if not args.wait:
        print("\nThe scheduler will fire it within ~15 seconds.")
        return

    print(f"\nwaiting up to {args.wait}s for the execution...")
    deadline = time.time() + args.wait
    while time.time() < deadline:
        conn = sqlite3.connect(DB)
        row = conn.execute(
            "select id, status, startedAt, stoppedAt from execution_entity "
            "where workflowId = ? and mode = 'trigger' order by id desc limit 1",
            (workflow_id,),
        ).fetchone()
        conn.close()
        if row and row[2] and row[2] >= now[:19]:
            print(f"execution: {row}")
            return
        time.sleep(5)
    print("no execution appeared within the wait window")


if __name__ == "__main__":
    main()
