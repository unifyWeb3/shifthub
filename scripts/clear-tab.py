#!/usr/bin/env python3
"""
Delete data rows from a ShiftHub sheet tab, through the Google Sheets API.

Used to clean up test/demo rows without opening the browser.

Important: the Sheets API takes the range to clear in the URL, not in the
request body - the body of a `:clear` call must be empty. The header row
(row 1) is never included in the cleared range.

Usage:
    python3 scripts/clear-tab.py SwapRequests
    python3 scripts/clear-tab.py SwapRequests --keep 3      # keep the newest 3 rows
    python3 scripts/clear-tab.py Flags
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

DEFAULT_SHEET_ID = read_rota.DEFAULT_SHEET_ID
access_token = read_rota.access_token
google_credential = read_rota.google_credential
read_tab = read_rota.read_tab

# https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{range}:clear
CLEAR_URL = "https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{range}:clear"


def clear_range(token: str, sheet_id: str, cell_range: str) -> None:
    """Clear the given A1 range. The range goes in the URL; the body is empty."""
    url = CLEAR_URL.format(id=sheet_id, range=urllib.parse.quote(cell_range))
    request = urllib.request.Request(
        url, data=b"", method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"error: Sheets API {error.code}: {error.read().decode()[:300]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tab")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--keep", type=int, default=0,
                        help="keep this many of the newest rows, delete the rest")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    token = access_token(google_credential())
    rows = read_tab(token, args.sheet_id, args.tab)
    print(f"tab '{args.tab}': {len(rows)} data row(s)")

    if args.keep >= len(rows):
        print("nothing to delete")
        return
    delete_count = len(rows) - args.keep
    first_to_delete = args.keep  # rows are read top-down, newest last
    start_row = first_to_delete + 2  # +1 for the header, +1 for 1-based index
    end_row = len(rows) + 1

    print(f"would clear rows {start_row}-{end_row} ({delete_count} row(s))")
    if args.dry_run:
        return

    clear_range(token, args.sheet_id, f"{args.tab}!{start_row}:{end_row}")
    print(f"cleared rows {start_row}-{end_row}")


if __name__ == "__main__":
    main()
