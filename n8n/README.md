# ShiftHub n8n workflows

Twelve importable workflow JSON files. Nothing here contains credentials or keys — you attach
your own credentials in the n8n UI after importing.

## Import (2 minutes)

```bash
# from the repo root
n8n import:workflow --separate --input=./n8n/workflows
# or one at a time
n8n import:workflow --input=./n8n/workflows/03-escalation-3hours-supervisor.json
```

In the n8n UI: **Workflows → ⋯ → Import from File** (repeat for each file), or drop them all in.

## Order to publish

Import all 12 first, then wire credentials, then publish in this order. In n8n 2.x the
**Active** toggle is called **Publish**; an unpublished workflow still runs when you click
**Execute Workflow** in the editor, but its schedule and webhook are off.

| # | File | Workflow | Publish when |
|---|------|----------|----------------|
| 1 | `10-seed-demo-data.json` | Seed Demo Data | After the Google Sheets credential works (run manually, not scheduled) |
| 2 | `04-telegram-yes-confirm.json` | Telegram YES Confirmation | After the Telegram bot credential exists |
| 3 | `05-email-link-confirm.json` | Email Confirmation Link | After the Google Sheets credential works |
| 4 | `06-email-reply-yes-confirm.json` | Email Reply YES Confirmation | After the IMAP credential exists |
| 5 | `07-swap-request-intake.json` | Swap Request Intake | After Google Sheets + SMTP + Telegram work (set `publicBaseUrl` first) |
| 6 | `11-dashboard-api.json` | Dashboard Data API | After Google Sheets works (needed by the Vercel app) |
| 7 | `01-daily-reminders-1day.json` | Daily 6PM Reminders | After SMTP + Telegram work |
| 8 | `02-reminders-2hours.json` | 2 Hours Before Reminders | After SMTP + Telegram work |
| 9 | `03-escalation-3hours-supervisor.json` | **3-Hour Unconfirmed Escalation** | After SMTP + Telegram work — this is the headline flow |
| 10 | `08-monthly-hours-summary.json` | Monthly Hours Summary | After Google Sheets + SMTP work |
| 11 | `09-understaffing-flag.json` | Understaffing Check & Flag | After Google Sheets + SMTP work |
| 12 | `12-error-notifier.json` | Error Notifier | Last — then set it as the Error Workflow on the other 11 |

## Credentials to attach (all created by you in the n8n UI)

| Workflow node | Credential type | What to enter |
|---|---|---|
| Every **Google Sheets** node | `Google Sheets OAuth2 API` (or *Google Service Account*) | Authorise the Google account that owns the rota sheet — see `docs/SETUP.md` |
| Every **Send Email** / **Email Send** node | `SMTP account` | `smtp.gmail.com`, port `587`, user = the facility mailbox, password = Google App Password |
| **Inbox Trigger** (workflow 06) | `IMAP account` | `imap.gmail.com`, port `993`, user = facility mailbox, password = Google App Password, TLS on |
| **Telegram Trigger** / **Telegram** nodes | `Telegram account` | Bot token from @BotFather |
| **Respond to Webhook** nodes | none | — |

## One manual edit in every workflow

Replace `PASTE_GOOGLE_SPREADSHEET_ID` with your sheet's ID (the long string in the sheet URL
between `/d/` and `/edit`). Fastest way: n8n → open each workflow → select the Google Sheets
node → paste the ID into the **Document ID** field. n8n's sheet picker lets you choose it from a
dropdown after you authenticate, which saves typing.

## Validate the JSON before importing

```bash
python3 scripts/validate_workflows.py
```

Checks node ids/names, connection targets, output-port arity, `$('Node')` references, expression
balance and credential leakage. It is a structural check, not a runtime test — always run one
workflow manually after connecting credentials.
