# Notes for your SIWES written report

Use these as a skeleton for the report chapters your organisation requires. Replace the bracketed
placeholders with your facility's details.

## 1. Problem statement

Clinical facilities lose shifts to a mundane chain of failures: a rota published in a spreadsheet
or group chat, no reliable reminder, no confirmation step, and no early warning when somebody
does not turn up. The consequences are missed shifts, unsafe staffing ratios, unpaid overtime,
staff stress, and supervisors discovering the gap when the ward is already short.

The objective was to build an automated shift-coverage system that:

1. keeps one authoritative rota sheet;
2. reminds each staff member 1 day and 2 hours before a shift;
3. captures confirmation with a simple `YES` reply;
4. accepts swap requests through a form;
5. alerts the supervisor exactly 3 hours before an unconfirmed shift;
6. produces a monthly hours summary; and
7. flags shifts that are staffed below the required headcount.

## 2. Scope and assumptions

- The system coordinates **staffing**, never patient care. No patient data is stored.
- Staff interact only through channels they already use (Telegram, email) plus one web form.
- The rota sheet in Google Sheets is the single source of truth; n8n is the process layer.
- The facility timezone is `Africa/Lagos`; all scheduling and date maths use it.
- A shift needs `requiredCount` confirmed staff members; fewer means "understaffed".

## 3. Methodology (what you actually did)

1. **Requirements analysis** — mapped the facility's existing manual workflow (paper rota, group
   chat, phone calls) to automatable events, and identified the "3-hour unconfirmed" event as the
   highest-value intervention because it is the last safe point to act.
2. **Data modelling** — designed a single-table-per-concern schema in Google Sheets
   (`Rota`, `Settings`, `SwapRequests`, `Flags`, `MonthlySummary`) with idempotency timestamps so
   reminders and alerts fire exactly once.
3. **Workflow design in n8n** — 12 workflows: five scheduled, four webhook/telegram triggered,
   one manual seed, one error handler. Scheduled flows follow the *Trigger → Fetch → Process →
   Deliver → Log* pattern; webhook flows follow *Receive → Validate → Transform → Respond/Notify*.
4. **Channel integration** — email over SMTP (Gmail app password), email inbox watching over
   IMAP for `YES` replies, and a Telegram bot for confirmations and supervisor alerts. Three
   confirmation paths converge on one write (`status = CONFIRMED`).
5. **Front end** — a static Vercel app (overview, swap request form, live dashboard) with
   serverless proxy functions so the n8n webhook URL is never exposed to the browser.
6. **Verification** — a structural validator for the workflow JSON
   (`scripts/validate_workflows.py`) plus manual execution of every flow against the seeded
   roster, including the 3-hour escalation test.
7. **Documentation & handover** — setup guide, demo script, architecture notes, and this
   repository.

## 4. Results (fill in from your demo)

| Objective | How it was verified | Result |
|---|---|---|
| Rota sheet | One Google Sheet, five tabs, one row per assignment | [done / date] |
| T-1 day reminder | Workflow 01 executed; `reminder1dSent` timestamp + message received | [ ] |
| T-2 hours reminder | Workflow 02 executed inside the 105–135 minute window | [ ] |
| YES to confirm | Telegram `YES`, email reply, and one-tap link each flipped `status` to `CONFIRMED` | [ ] |
| Swap request form | Form submission → `SwapRequests` row + supervisor notification | [ ] |
| **3-hour supervisor alert** | Seeded a shift starting in ~3 h with `PENDING` staff → workflow 03 alerted the supervisor by email + Telegram | [ ] |
| Monthly hours summary | Workflow 08 produced the supervisor table and `MonthlySummary` rows (overnight shifts counted correctly) | [ ] |
| Understaffing flag | Workflow 09 flagged the short shift and logged it in `Flags` | [ ] |

## 5. Benefits (suggested wording, adjust to your facility's reality)

- **Earlier detection.** The supervisor learns about a gap three hours before the shift, when
  cover can still be arranged, instead of at handover.
- **Less chasing.** Confirmation status is visible in one column, so nobody has to phone around
  to find out who is coming in.
- **A record of swaps.** Every request is timestamped, attributed and linked to a rota row.
- **Fair, automatic hours.** Hours are computed from confirmed shifts instead of reconstructed
  from memory at month end.
- **Reusable design.** The same twelve workflows run for a clinic, a care home or a hospital —
  only the Settings tab changes.

## 6. Limitations and future work

- Staff reminders rely on people noticing Telegram and email; no push channel yet.
- Swap requests need a human decision (correct for staffing, but it is still manual work).
- The dashboard is read-only and unauthenticated; add role-based access before real deployment.
- The rota is hand-maintained in Sheets — a staff self-service roster (staff propose their own
  availability) is the natural next module.
- Extend to: sickness reporting, agency cover requests, skill-mix checks (e.g. at least one
  senior nurse per shift), and payroll export.

## 7. Conclusion

ShiftHub demonstrates that a small, auditable automation layer over the rota a facility already
uses can remove most of the avoidable causes of missed shifts. The "done when" criterion — an
unconfirmed shift alerting the supervisor at the 3-hour mark — was met and demonstrated
end-to-end.

## 8. Appendices to attach

- `docs/ARCHITECTURE.md` (system design and data model)
- `docs/SETUP.md` (installation and configuration)
- `docs/DEMO-GUIDE.md` (the walkthrough you gave)
- `n8n/workflows/*.json` (the actual workflows — export from your n8n instance after import so
  the file includes your own node positions)
- Screenshots listed at the end of `docs/DEMO-GUIDE.md`
- The `Rota` sheet extract (anonymised if required by your organisation)
