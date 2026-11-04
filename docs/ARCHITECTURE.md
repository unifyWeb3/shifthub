# Architecture

## The moving parts

```
        ┌──────────────────────────── Google Sheets ────────────────────────────┐
        │  Rota   Settings   SwapRequests   Flags   MonthlySummary              │
        └───────▲───────────────────────▲───────────────────────▲───────────────┘
                │ read/write            │ read/write            │ read
     ┌──────────┴─────────────────────────────────────────────────┴───────────┐
     │                     n8n (12 workflows, cron + webhooks)                 │
     │  01 T-1 reminder   02 T-2h reminder   03 3-hour escalation             │
     │  04 Telegram YES   05 email link      06 email reply YES              │
     │  07 swap intake    08 monthly hours   09 understaffing flags          │
     │  10 demo seed      11 dashboard API   12 error notifier                │
     └───────▲───────────────────────────▲──────────────────────────▲──────────┘
             │ email (SMTP)                │ Telegram bot           │
        ┌────┴─────┐                 ┌────┴──────┐          ┌───────┴────────┐
        │  Staff   │                 │  Supervisor│          │ Vercel web app │
        │ reminders│                 │  alerts    │          │ swap + dashboard│
        └──────────┘                 └────────────┘          └────────────────┘
```

The Vercel app never talks to Google Sheets directly. It posts to `/api/*` serverless functions
that forward to n8n webhooks — so the webhook URL stays server-side (no URL in client code) and
n8n keeps ownership of every write.

## Data model

One spreadsheet, five tabs.

**`Rota` — one row per assignment.** A shift with three staff members is three rows sharing the
same `shiftId`; `requiredCount` is repeated on each row. That makes every row independently
updatable (a YES from one person touches one row) while the shift-level views are computed by
grouping on `shiftId`.

Status machine:

| Status | Meaning | Who sets it |
|---|---|---|
| `PENDING` | Booked, not yet confirmed | Rota design / seed |
| `CONFIRMED` | Staff replied YES (or tapped the link) | Workflows 04, 05, 06 |
| `DECLINED` | Staff cannot attend | Manual (supervisor) |
| `SWAPPED` | Reassigned to another staff member | Manual (supervisor), after a swap request |

Timestamps (`reminder1dSent`, `reminder2hSent`, `escalation3hSent`) make the system
**idempotent**: a reminder or an escalation is sent once per assignment, no matter how often the
cron fires. This is why the source of truth is the sheet and not n8n memory.

## The twelve workflows

| # | Trigger | What it does | Writes |
|---|---------|--------------|--------|
| 01 | Cron `0 18 * * *` | Reminds everyone booked for tomorrow | `reminder1dSent` |
| 02 | Cron `*/15 * * * *` | Reminds everyone starting in ~2 hours | `reminder2hSent` |
| 03 | Cron `*/15 * * * *` | **Alerts the supervisor about shifts starting in ~3 hours that are still PENDING** | `escalation3hSent` |
| 04 | Telegram message | `YES` confirms the nearest pending shift | `status` |
| 05 | Webhook `GET /webhook/confirm-shift` | One-tap confirmation from the email link | `status` |
| 06 | IMAP inbox | `YES` as an email reply confirms the shift | `status` |
| 07 | Webhook `POST /webhook/swap-request` | Validates + logs a swap request, notifies the supervisor | `SwapRequests` row |
| 08 | Cron `0 8 1 * *` | Previous month's hours per staff member | `MonthlySummary` rows |
| 09 | Cron `0 7 * * *` | Flags shifts below required headcount for 14 days | `understaffedFlag`, `Flags` rows |
| 10 | Manual | Seeds demo data with relative dates (incl. a shift starting in ~3 hours) | `Rota` rows |
| 11 | Webhook `GET /webhook/shifthub-dashboard` | JSON coverage payload for the dashboard | — |
| 12 | Error Trigger | Emails + Telegrams the supervisor when any workflow fails | — |

## Timing logic

Two windows, both tolerant of the 15-minute cron cadence:

- **T-2 hours** → start time is 105–135 minutes away.
- **T-3 hours** → start time is 165–195 minutes away.

A shift therefore enters the 3-hour window for roughly two consecutive cron runs, and the
`escalation3hSent` stamp makes sure the supervisor is told **once**, not twice.

All date maths uses Luxon (`DateTime`) inside Code nodes, in the facility timezone from the
`Settings` tab (`Africa/Lagos` by default). Overnight shifts (`19:00 → 07:00`) are handled by
adding 24 hours when the end time is not after the start time — this matters for both the
reminder windows and the monthly hours total.

## Design decisions

**Why Google Sheets and not a database?** It is the artefact the facility already has. Ward
managers can open and correct it without training, IT does not have to host anything, and the
SIWES panel can see a real rota in the demo instead of a mock UI. The trade-off (row-level
updates, no transactions) is acceptable at ward scale.

**Why Code nodes?** The skills guidance for n8n is native-node-first, and that is where native
nodes are used: IF for routing, Split Out for the flags list, Sheets for I/O. Code appears only
for things no native node expresses — Luxon date windows, group-by-shift aggregation, message
composition and interval maths. Each Code node carries a `Why Code:` note in the node notes.

**Why three confirmation channels?** Staff reply the way they already talk. Telegram is fastest
and gives a read receipt; the email link is the fallback when someone has no Telegram; the email
reply keeps the promise "reply YES" literal. All three converge on the same write:
`status = CONFIRMED` on one row.

**Why does the Vercel app use serverless functions?** A browser cannot call `http://localhost:5678`
from a deployed site, and calling n8n directly from the browser would expose the webhook URL and
hit CORS. The tiny `/api/*` functions solve both and give a clean place to add an API key later.

## Security and privacy notes

- No credentials, tokens or sheet IDs are committed to the repository; every credential lives in
  n8n's credential store.
- The dashboard endpoint is unauthenticated read-only JSON (names, roles, wards, times). Add an
  API-key header check before using it for real staff data.
- The rota contains personal data. Keep sharing restricted to the facility's Google account /
  service account, and keep patient data out of it entirely.
- The Telegram bot token is a credential in n8n — if it leaks, revoke it with @BotFather
  (`/revoke`) and issue a new one.

## Known limits (and what to do about them)

| Limit | Mitigation / next step |
|---|---|
| Sheets API write quota (60 writes/min per project) | Batch writes if a facility ever exceeds a few hundred assignments per run. |
| Cron granularity of 15 minutes | The ±15-minute windows are deliberate; tighten by increasing the cron frequency (and narrowing the windows). |
| IMAP "YES" parsing is literal | Works for "YES", "yes", "ok", "confirm"; a longer email reply is ignored on purpose. |
| No staff-facing auth | Anyone can post a swap request. Add the API-key check or a signed link per staff member. |
| Swap requests are not auto-approved | A human approves — deliberately: clinical cover decisions should not be automated. |
