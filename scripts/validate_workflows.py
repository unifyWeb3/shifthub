#!/usr/bin/env python3
"""
ShiftHub workflow validator.
Structural + reference checks for hand-authored n8n workflow JSON:
  * JSON shape, unique node ids/names, known node types
  * connections reference real nodes; output-port counts respect node arity
  * every $('Node Name') reference resolves to a node in the same workflow
  * {{ }} balance, no credentials embedded, placeholder census
Exits non-zero on any ERROR. WARNs are listed but don't fail the build.
Usage: python3 scripts/validate_workflows.py [workflows_dir]
"""
import json, re, sys, uuid
from pathlib import Path

WF_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "n8n" / "workflows"

KNOWN_TYPES = {
    "n8n-nodes-base.cron": 1,
    "n8n-nodes-base.manualTrigger": 1,
    "n8n-nodes-base.webhook": 2,
    "n8n-nodes-base.respondToWebhook": 1,
    "n8n-nodes-base.if": 2,
    "n8n-nodes-base.code": 2,
    "n8n-nodes-base.googleSheets": 4.5,
    "n8n-nodes-base.telegram": 1,
    "n8n-nodes-base.telegramTrigger": 1,
    "n8n-nodes-base.emailSend": 2,
    "n8n-nodes-base.emailReadImap": 2,
    "n8n-nodes-base.splitOut": 1,
    "n8n-nodes-base.errorTrigger": 1,
    "n8n-nodes-base.stickyNote": 1,
}
TRIGGERS = {"cron", "manualTrigger", "webhook", "telegramTrigger", "emailReadImap", "errorTrigger"}
MAX_OUTPUTS = {"if": 2}  # everything else: single main output
SPREADSHEET_PLACEHOLDER = "PASTE_GOOGLE_SPREADSHEET_ID"

errors, warns = [], []

def err(f, msg): errors.append(f"{f}: {msg}")
def warn(f, msg): warns.append(f"{f}: {msg}")

def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)

def check_workflow(path: Path):
    f = path.name
    try:
        wf = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(f, f"invalid JSON: {e}")
        return

    for key in ("name", "nodes", "connections", "settings"):
        if key not in wf:
            err(f, f"missing top-level key '{key}'")
    nodes = wf.get("nodes", [])
    connections = wf.get("connections", {})
    if not isinstance(nodes, list) or not isinstance(connections, dict):
        err(f, "nodes must be a list, connections a dict")
        return

    names, ids = {}, {}
    for node in nodes:
        for req in ("id", "name", "type", "typeVersion", "position", "parameters"):
            if req not in node:
                err(f, f"node {node.get('name', '?')!r} missing '{req}'")
        nid, nname = node.get("id"), node.get("name")
        ntype = node.get("type", "")
        sticky = ntype == "n8n-nodes-base.stickyNote"
        if nid in ids:
            err(f, f"duplicate node id {nid}")
        ids[nid] = nname
        if not sticky:
            if nname in names:
                err(f, f"duplicate node name {nname!r}")
            names[nname] = node
            try:
                uuid.UUID(str(nid))
            except ValueError:
                err(f, f"node {nname!r}: id is not a UUID ({nid!r})")
        if ntype not in KNOWN_TYPES:
            warn(f, f"node {nname!r}: unrecognized type {ntype!r} (version drift?)")
        elif node.get("typeVersion") != KNOWN_TYPES[ntype]:
            warn(f, f"node {nname!r}: typeVersion {node.get('typeVersion')} (expected {KNOWN_TYPES[ntype]})")
        pos = node.get("position")
        if not (isinstance(pos, list) and len(pos) == 2 and all(isinstance(p, (int, float)) for p in pos)):
            err(f, f"node {nname!r}: position must be [x, y] numbers")
        if "credentials" in node:
            err(f, f"node {nname!r}: credentials embedded in JSON — remove them, users add their own")

    # connections
    for src, outs in connections.items():
        if src not in names:
            err(f, f"connection source {src!r} is not a node")
            continue
        main = outs.get("main") if isinstance(outs, dict) else None
        if not isinstance(main, list):
            err(f, f"connection from {src!r}: missing 'main' array")
            continue
        short = src_type = None
        src_type = names[src]["type"].split(".")[-1]
        max_ports = MAX_OUTPUTS.get(src_type, 1)
        if len(main) > max_ports:
            err(f, f"connection from {src!r}: {len(main)} output ports (max {max_ports} for {src_type})")
        for port_idx, port in enumerate(main):
            if not isinstance(port, list):
                err(f, f"connection from {src!r} port {port_idx}: must be a list")
                continue
            for link in port:
                tgt = link.get("node")
                if link.get("type") != "main":
                    err(f, f"connection {src!r} -> {tgt!r}: type must be 'main'")
                if tgt not in names:
                    err(f, f"connection {src!r} -> {tgt!r}: target node does not exist")

    # incoming connectivity (non-sticky, non-trigger must have a parent)
    targeted = set()
    for outs in connections.values():
        for port in outs.get("main", []):
            for link in port:
                targeted.add(link.get("node"))
    for nname, node in names.items():
        ntype = node["type"].split(".")[-1]
        if ntype in TRIGGERS:
            continue
        if nname not in targeted:
            err(f, f"node {nname!r}: no incoming connections (orphaned)")

    # $('Node') references inside expressions must resolve
    ref_re = re.compile(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)")
    for s in walk_strings(wf):
        for m in ref_re.finditer(s):
            if m.group(1) not in names:
                err(f, f"expression reference $('{m.group(1)}') does not match any node in this workflow")
        # {{ }} balance (rough but catches the common break)
        if s.count("{{") != s.count("}}"):
            err(f, f"unbalanced {{ }} in string: {s[:120]!r}")

    # secrets / placeholders
    for s in walk_strings(wf):
        for pat in (r"(?i)bearer\s+[A-Za-z0-9._-]{10,}", r"(?i)api[_-]?key\s*[:=]", r"(?i)password\s*[:=]"):
            if re.search(pat, s):
                warn(f, f"possible embedded secret in string: {s[:80]!r}")
    placeholder_count = sum(1 for s in walk_strings(wf) if SPREADSHEET_PLACEHOLDER in s)
    if placeholder_count:
        warn(f, f"{placeholder_count}x {SPREADSHEET_PLACEHOLDER} — paste your Google Sheet ID before activating")

def main():
    files = sorted(WF_DIR.glob("*.json"))
    if not files:
        print(f"no workflow JSON files found in {WF_DIR}")
        return 1
    for f in files:
        check_workflow(f)
    print(f"\nChecked {len(files)} workflow(s) in {WF_DIR}\n")
    if warns:
        print(f"WARNINGS ({len(warns)}):")
        for w in warns:
            print("  !", w)
        print()
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print("  x", e)
        print("\nFAILED")
        return 1
    print("All workflows structurally valid.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
