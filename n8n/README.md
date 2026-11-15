# ShiftHub n8n workflows

Thirteen importable workflow JSON files (01–12 are the functional workflows, 13 is a maintenance
helper). Nothing here contains credentials or keys — you attach your own credentials in the n8n
UI after importing.

## Import (2 minutes)

```bash
# from the repo root
n8n import:workflow --separate --input=./n8n/workflows
# or one at a time
n8n import:workflow --input=./n8n/workflows/03-escalation-3hours-supervisor.json
```

In the n8n UI: **Workflows → ⋯ → Import from File** (repeat for each file), or drop them all in.

## The public webhooks (short paths)

| URL | Used by |
|---|---|
| `GET  /webhook/shifthub-dashboard` | the Vercel dashboard (`/api/dashboard`) |
| `POST /webhook/swap-request` | the Vercel swap form (`/api/swap`) |
| `GET  /webhook/confirm-shift?token=…` | the one-tap link inside every reminder e-mail |

In n8n 2.x a Webhook node without a `webhookId` is served from
`/webhook/<workflowId>/<lowercased node name>/<path>`. That long form contains the workflow id
and breaks when the node name has a space (the incoming path is URL-decoded before the lookup, so
`%20` can never match). The webhook nodes in workflows 05, 07 and 11 therefore carry an explicit
`webhookId` (`confirm-shift`, `swap-request`, `shifthub-dashboard`), which is what produces the
short paths above.

If you import into a fresh instance and the paths look wrong:

```bash
python3 scripts/sync-webhook-paths.py --force   # copies webhookId into the instance
python3 scripts/publish-drafts.py               # re-snapshots the drafts as published versions
```

## Order to publish

Import all 13 first, then wire credentials, then publish in this order. In n8n 2.x the
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
| — | `13-sync-public-base-url.json` | Maintenance: Set Public Base URL | Never published — manual trigger only, run by `scripts/sync-tunnel-url.py` |

> n8n runs the **published snapshot**, not the draft in the editor. Wire the credential, then
> publish again. From the CLI: `n8n publish:workflow --id=<id>`, or `python3 scripts/publish-drafts.py`
> for all of them at once.

## Credentials to attach (all created by you in the n8n UI)

| Workflow node | Credential type | What to enter |
|---|---|---|
| Every **Google Sheets** node | `Google Sheets OAuth2 API` (or *Google Service Account*) | Authorise the Google account that owns the rota sheet — see `docs/SETUP.md` |
| Every **Send Email** / **Email Send** node | `SMTP account` | `smtp.gmail.com`, port `587`, user = the facility mailbox, password = Google App Password |
| **Inbox Trigger** (workflow 06) | `IMAP account` | `imap.gmail.com`, port `993`, user = facility mailbox, password = Google App Password, TLS on |
| **Telegram Trigger** / **Telegram** nodes | `Telegram account` | Bot token from @BotFather |
| **Respond to Webhook** nodes | none | — |

Faster than the UI, and the secret never touches a web form:

```bash
python3 scripts/add-credential.py telegram
python3 scripts/add-credential.py smtp
python3 scripts/add-credential.py imap
```

Each script creates the credential in the local n8n instance and wires it into every matching
node (`scripts/wire-credential.py`).

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
