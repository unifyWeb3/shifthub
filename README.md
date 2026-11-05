# ShiftHub

**Every shift, covered.** An n8n-powered shift-coverage automation system for clinics, care
homes and hospitals — built as a SIWES industrial training project.

One Google Sheet holds the rota. Twelve n8n workflows remind staff, capture their `YES`,
escalate gaps to the supervisor before the shift starts, log swap requests, flag understaffed
units and total hours every month.

> **The "done when" criterion:** a shift that is still unconfirmed **3 hours before it starts**
> automatically alerts the supervisor (email + Telegram). Demonstrated end-to-end — see
> [`docs/DEMO-GUIDE.md`](docs/DEMO-GUIDE.md).

---

## What it does

| Requirement | Where it lives |
|---|---|
| Rota sheet | Google Sheets — `Rota`, `Settings`, `SwapRequests`, `Flags`, `MonthlySummary` tabs |
| Reminder 1 day before | Workflow **01** — cron `0 18 * * *`, email + Telegram |
| Reminder 2 hours before | Workflow **02** — cron `*/15 * * * *`, email + Telegram |
| `YES` reply to confirm | Workflows **04** (Telegram), **06** (email reply via IMAP), **05** (one-tap email link) |
| Swap request form | Workflow **07** + the Vercel app's `/swap` page |
| Supervisor alert 3 hours before an unconfirmed shift | Workflow **03** — the headline flow. The alert is sent *before* the row is stamped, so a failed send is retried rather than silently dropped. |
| Monthly hours summary | Workflow **08** — per-staff hours, supervisor report, `MonthlySummary` tab |
| Flag shifts with too few staff | Workflow **09** — daily 07:00 sweep, `understaffedFlag` + `Flags` tab + supervisor alert |
| Bonus: failures are never silent | Workflow **12** — error notifier wired as the error workflow on the others |
| Bonus: live supervisor view | Workflow **11** + the Vercel app's `/dashboard` page |

## Architecture in one picture

```
Google Sheets  ⇄  n8n (12 workflows)  ⇄  Staff & Supervisor (Telegram + Email)
                                   ⇅
                          Vercel web app (/swap, /dashboard)
```

The rota sheet is the database *and* the audit trail. n8n is the process layer. The web app never
touches Google Sheets directly — it goes through n8n webhooks, so every write is owned by one
system. Full details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Quick start (60 minutes, first time)

1. **Create the sheet** — 5 tabs with the headers in [`sheets/README.md`](sheets/README.md).
2. **Run n8n** — `npm install -g n8n && TZ=Africa/Lagos n8n start` (Docker alternative in the
   setup guide).
3. **Import the workflows** — `n8n import:workflow --separate --input=./n8n/workflows`, then paste
   your spreadsheet ID and attach your Google Sheets, SMTP, IMAP and Telegram credentials.
4. **Seed demo data** — run workflow **10**, then run workflow **03** to watch the 3-hour
   supervisor alert fire.
5. **Point the deployed app at your n8n instance** — the Vercel project is already live and
   linked to this repo, so it redeploys on every push. Add the `N8N_WEBHOOK_BASE` environment
   variable (your n8n public URL) in the Vercel dashboard under **Project → Settings →
   Environment Variables**, then redeploy.

Full step-by-step: [`docs/SETUP.md`](docs/SETUP.md) · Demo script: [`docs/DEMO-GUIDE.md`](docs/DEMO-GUIDE.md)

## The web app (Vercel) — already deployed

**Live site: <https://shifthub-oxunify.vercel.app>** (production, linked to the GitHub repo — every
push redeploys it automatically).

| Page | What it does |
|---|---|
| `/` | Project overview: the problem, how it works, the architecture |
| `/swap` | Swap request form → `POST /api/swap` → n8n `POST /webhook/swap-request` |
| `/dashboard` | Live coverage for the next 14 days → `GET /api/dashboard` → n8n `GET /webhook/shifthub-dashboard` |

Static HTML/CSS/JS with two dependency-free Vercel serverless functions. If
`N8N_WEBHOOK_BASE` is unset, the site runs in a clearly-labelled offline demo mode instead of
breaking.

## Repository layout

```
n8n/
  workflows/        12 importable workflow JSON files (no credentials inside)
  README.md         import order, credential matrix, publishing checklist
sheets/
  settings.csv      ready-to-import Settings tab
  rota-example.csv  12 worked example assignments
  *-headers.csv     header rows for the three write tabs
  README.md         exact tab + column definitions
webapp/             the Vercel front end (static pages + api/ proxy functions)
docs/
  SETUP.md          installation, credentials, publishing, troubleshooting
  DEMO-GUIDE.md     the 10-minute walkthrough for your supervisor
  ARCHITECTURE.md   data model, workflow catalogue, timing logic, limits
  SIWES-REPORT-NOTES.md  skeleton for your written report
scripts/
  validate_workflows.py  structural validator for the workflow JSON
```

## Validate the workflows

```bash
python3 scripts/validate_workflows.py
```

Checks node ids and names, connection targets, output-port arity, every `$('Node')` expression
reference, `{{ }}` balance, and that no credentials are committed. It also prints a census of the
`PASTE_GOOGLE_SPREADSHEET_ID` markers so you know exactly what still needs filling in. It runs in
CI on every push (`.github/workflows/validate.yml`).

## Built with

- [n8n](https://n8n.io) — workflow automation (12 workflows, cron + webhook + telegram + IMAP)
- Google Sheets — rota store, settings, flags, monthly summary
- Telegram Bot API — staff confirmations and supervisor alerts
- Gmail SMTP / IMAP — email reminders, `YES` replies, reports
- Vercel — static front end + two serverless proxy functions
- Vanilla HTML/CSS/JS — no framework, no build step, no client-side dependencies

## What you have to do yourself

These need accounts only you can create (each takes 5–15 minutes):

1. Create the Google Sheet + share it with your n8n Google credential.
2. Create a Telegram bot with **@BotFather** and paste the token into an n8n credential.
3. Create a Gmail **App Password** for the SMTP (send) and IMAP (read) credentials.
4. Paste your spreadsheet ID into the Google Sheets nodes (search the repo for
   `PASTE_GOOGLE_SPREADSHEET_ID`).
5. Add `N8N_WEBHOOK_BASE` to the Vercel project (it is already deployed and linked to this repo)
   so the site talks to your n8n instance instead of the offline demo data.
6. Put your supervisor's email and Telegram chat id in the `Settings` tab.

## Safety

This is a staffing tool: it never stores patient data. The rota contains staff contact details —
keep the sheet restricted to facility staff, and revoke the Telegram bot token immediately if it
is ever exposed.

## Licence

MIT — see [`LICENSE`](LICENSE). Built for SIWES industrial training; free to use and adapt for
clinics, care homes and hospitals with attribution.
