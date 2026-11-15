#!/usr/bin/env python3
"""
Keep the public n8n URL in sync everywhere it is used.

A Cloudflare *quick* tunnel hands out a new random URL every time it restarts,
so the URL has to be pushed into four places:

  1. the n8n systemd unit  (N8N_WEBHOOK_URL / WEBHOOK_URL)
  2. the Settings tab in Google Sheets (publicBaseUrl) - used to build the
     one-tap confirmation link inside the reminder e-mails
  3. workflow 13 in n8n (the maintenance workflow that writes #2)
  4. Vercel (N8N_WEBHOOK_BASE) - the web app proxies to this URL

Steps 1-3 are done here. Step 4 is printed at the end (set it in the Vercel
dashboard: project `shifthub`, variable `N8N_WEBHOOK_BASE`).

Usage:
    python3 scripts/sync-tunnel-url.py [--url https://....trycloudflare.com] [--dry-run]
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

UNIT = Path.home() / ".config/systemd/user/shifthub-n8n.service"
TUNNEL_LOG = Path.home() / ".config/shifthub/tunnel.log"
DB = Path.home() / ".n8n" / "database.sqlite"
N8N_BIN = os.environ.get("N8N_BIN") or str(Path.home() / ".local/bin/n8n")
SERVICE = "shifthub-n8n"
MAINTENANCE_WORKFLOW = "ShiftHub — 13 · Maintenance: Set Public Base URL"
PLACEHOLDER = "PASTE_PUBLIC_BASE_URL"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def current_tunnel_url() -> str:
    if not TUNNEL_LOG.is_file():
        fail(f"no tunnel log at {TUNNEL_LOG}")
    urls = URL_RE.findall(TUNNEL_LOG.read_text(encoding="utf-8", errors="replace"))
    if not urls:
        fail(f"no trycloudflare URL in {TUNNEL_LOG}")
    return urls[-1]


def service_state() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def service(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=False)


def update_unit(url: str, dry_run: bool) -> bool:
    if not UNIT.is_file():
        fail(f"no systemd unit at {UNIT}")
    text = UNIT.read_text(encoding="utf-8")
    changed = False
    for key in ("N8N_WEBHOOK_URL", "WEBHOOK_URL"):
        pattern = re.compile(rf"^Environment={key}=.*$", re.MULTILINE)
        if pattern.search(text):
            new_text, count = pattern.subn(f"Environment={key}={url}", text)
            if count:
                text = new_text
                changed = True
        else:
            text = text.replace(
                "ExecStart=",
                f"Environment={key}={url}\nExecStart=",
                1,
            )
            changed = True
    if changed and not dry_run:
        UNIT.write_text(text, encoding="utf-8")
    return changed


def patch_maintenance_workflow(url: str, dry_run: bool) -> str | None:
    """Put the live URL into workflow 13 and return its workflow id."""
    if not DB.is_file():
        fail(f"no n8n database at {DB}")
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select id, nodes from workflow_entity where name = ?", (MAINTENANCE_WORKFLOW,)
    ).fetchone()
    if not row:
        conn.close()
        print(f"  ! workflow '{MAINTENANCE_WORKFLOW}' is not in this n8n instance - skipped")
        return None
    workflow_id, nodes_json = row
    nodes = json.loads(nodes_json)
    changed = False
    for node in nodes:
        if node.get("type") != "n8n-nodes-base.googleSheets":
            continue
        columns = node.get("parameters", {}).get("columns", {})
        value = columns.get("value", {})
        if value.get("value") != url:
            value["value"] = url
            columns["value"] = value
            node["parameters"]["columns"] = columns
            changed = True
    if changed and not dry_run:
        conn.execute(
            "update workflow_entity set nodes = ?, updatedAt = CURRENT_TIMESTAMP where id = ?",
            (json.dumps(nodes, separators=(",", ":")), workflow_id),
        )
        for (version_nodes,) in conn.execute(
            "select nodes from workflow_history where workflowId = ?", (workflow_id,)
        ).fetchall():
            history_nodes = json.loads(version_nodes)
            for node in history_nodes:
                if node.get("type") != "n8n-nodes-base.googleSheets":
                    continue
                columns = node.get("parameters", {}).get("columns", {})
                value = columns.get("value", {})
                if value.get("value") != url:
                    value["value"] = url
                    columns["value"] = value
                    node["parameters"]["columns"] = columns
                    changed = True
            if changed:
                conn.execute(
                    "update workflow_history set nodes = ?, updatedAt = CURRENT_TIMESTAMP "
                    "where workflowId = ? and versionId = "
                    "(select versionId from workflow_history where workflowId = ? limit 1)",
                    (json.dumps(history_nodes, separators=(",", ":")), workflow_id, workflow_id),
                )
        conn.commit()
    conn.close()
    return workflow_id


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
                if payload.get("key") == "publicBaseUrl":
                    print(f"  Settings.publicBaseUrl = {payload.get('value')}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="explicit tunnel URL (default: read from the tunnel log)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    url = args.url or current_tunnel_url()
    print(f"public n8n URL: {url}\n")

    print("1. systemd unit")
    changed = update_unit(url, args.dry_run)
    print(f"   {'would update' if args.dry_run and changed else 'updated'}: {UNIT}")
    if not args.dry_run:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        print("   restarting n8n...")
        service("restart")
        for _ in range(30):
            time.sleep(2)
            if service_state() == "active":
                break
        print(f"   n8n is {service_state()}")
        health = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{url}/healthz"],
            capture_output=True, text=True)
        print(f"   tunnel /healthz -> {health.stdout.strip()}")

    print("\n2. n8n maintenance workflow (13)")
    workflow_id = patch_maintenance_workflow(url, args.dry_run)
    if workflow_id and not args.dry_run:
        print(f"   workflow id: {workflow_id}")
        ok = run_workflow(workflow_id)
        print(f"   Settings update: {'ok' if ok else 'FAILED'}")

    print("\n3. Vercel")
    print(f"   set N8N_WEBHOOK_BASE={url} in the Vercel project 'shifthub' (team oxunify)")
    print("   then redeploy so the web app proxy picks it up.")


if __name__ == "__main__":
    main()
