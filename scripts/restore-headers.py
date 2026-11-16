#!/usr/bin/env python3
"""
Restore the header row of a ShiftHub sheet tab.

Why this exists:
    `clear-tab.py` deletes data rows. If it is ever run against a tab whose
    header row is missing, the write workflows fail with "Column names were
    updated after the node's setup". This script puts the canonical header
    back, using the exact lists from sheets/README.md.

Usage:
    python3 scripts/restore-headers.py SwapRequests
    python3 scripts/restore-headers.py --all
"""
import argparse
import importlib.util
import json
import urllib.parse
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "read_rota", Path(__file__).resolve().parent / "read-rota.py"
)
read_rota = importlib.util.module_from_spec(spec)
spec.loader.exec_module(read_rota)

HEADERS = {
    "Rota": ["shiftId", "date", "startTime", "endTime", "ward", "role", "requiredCount",
             "staffId", "staffName", "email", "telegramChatId", "assignmentId", "status",
             "confirmToken", "reminder1dSent", "reminder2hSent", "escalation3hSent",
             "understaffedFlag"],
    "Settings": ["key", "value"],
    "SwapRequests": ["requestId", "createdAt", "assignmentId", "shiftId", "date", "startTime",
                     "endTime", "ward", "role", "requestorName", "requestorContact",
                     "targetPreference", "reason", "status"],
    "Flags": ["flaggedAt", "shiftId", "date", "startTime", "ward", "role", "requiredCount",
              "confirmedCount", "missingCount", "message", "flagKey"],
    "MonthlySummary": ["month", "staffId", "staffName", "shiftsConfirmed", "hoursWorked",
                       "generatedAt", "summaryKey"],
}

UPDATE_URL = "https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{range}?valueInputOption=RAW"


def current_rows(token: str, sheet_id: str, tab: str) -> list[list[str]]:
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
           f"/values/{urllib.parse.quote(tab)}")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode()).get("values") or []


def write_header(token: str, sheet_id: str, tab: str, header: list[str]) -> None:
    cell_range = f"{tab}!1:1"
    url = UPDATE_URL.format(id=sheet_id, range=urllib.parse.quote(cell_range))
    # The range in the URL and the range in the body have to be the same, or
    # the Sheets API rejects the request with INVALID_ARGUMENT.
    payload = {"range": cell_range, "majorDimension": "ROWS", "values": [header]}
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tab", nargs="?", choices=sorted(HEADERS))
    parser.add_argument("--all", action="store_true", help="check every tab")
    parser.add_argument("--sheet-id", default=read_rota.DEFAULT_SHEET_ID)
    args = parser.parse_args()

    token = read_rota.access_token(read_rota.google_credential())
    tabs = sorted(HEADERS) if args.all else [args.tab]

    for tab in tabs:
        expected = HEADERS[tab]
        rows = current_rows(token, args.sheet_id, tab)
        actual = rows[0] if rows else None
        if actual == expected:
            print(f"{tab}: header is correct")
            continue
        if actual:
            print(f"{tab}: header differs -> {actual}")
        else:
            print(f"{tab}: header is MISSING -> restoring")
        write_header(token, args.sheet_id, tab, expected)
        print(f"  restored {len(expected)} column(s)")


if __name__ == "__main__":
    main()
