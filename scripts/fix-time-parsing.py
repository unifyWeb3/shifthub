#!/usr/bin/env python3
"""
Fix the shift-time parsing bug across every ShiftHub workflow.

The bug
-------
Google Sheets returns a time cell as `7:00` (single-digit hour) when the
column is formatted that way, but as `07:00` when it is not. Luxon's
`DateTime.fromFormat(..., 'yyyy-MM-dd HH:mm')` rejects `7:00` with
"unparsable", so every workflow that parses `date + startTime` silently
dropped those shifts:

  - 08 Monthly Hours Summary : hoursWorked was NaN -> the sheet cell was empty
                                and the supervisor email said "NaN"
  - 02 / 03                  : a shift starting at 7:00 or 9:00 was skipped,
                                so the 2-hour reminder or the 3-hour escalation
                                never fired for it
  - 11 Dashboard             : minutesUntilStart was null, no 3-hour banner
  - 04 / 06                  : a YES reply could not match that shift

The fix
-------
Use Luxon's `H:mm` (single-or-double digit hour) instead of `HH:mm`. It
parses `7:00`, `07:00`, `9:00` and `19:00` alike.

Usage:
    python3 scripts/fix-time-parsing.py [--check]
"""
import argparse
import json
import sys
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / "n8n" / "workflows"
OLD = "yyyy-MM-dd HH:mm"
NEW = "yyyy-MM-dd H:mm"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="only report what would change")
    args = parser.parse_args()

    changed = 0
    total = 0
    for path in sorted(WORKFLOWS.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        count = raw.count(OLD)
        if not count:
            continue
        total += count
        print(f"{path.name}: {count} occurrence(s)")
        if args.check:
            continue
        data = json.loads(raw)
        touched = []
        for node in data.get("nodes", []):
            code = (node.get("parameters") or {}).get("jsCode")
            if isinstance(code, str) and OLD in code:
                node["parameters"]["jsCode"] = code.replace(OLD, NEW)
                touched.append(node.get("name"))
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed += count
        print(f"  fixed in: {', '.join(touched)}")

    print(f"\n{'would fix' if args.check else 'fixed'} {changed} of {total} occurrence(s)")
    if args.check and total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
