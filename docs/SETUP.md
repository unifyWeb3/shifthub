# ShiftHub setup guide

Everything you need to go from a blank machine to a working demo. Budget ~60 minutes the first
time; each later run takes minutes.

> **Data rule:** this rota contains staff names, emails, Telegram ids and shift times. Never put
> patient information in it. ShiftHub is a staffing tool, not a clinical record.

---

## 0. What you need before you start

| Need | Why | Free? |
|---|---|---|
| A Google account | Owns the rota spreadsheet, sends the emails | Yes |
| A Telegram account + the `@BotFather` bot | Staff confirmations and supervisor alerts | Yes |
| Node.js 20+ on the machine running n8n | n8n itself | Yes |
| A Vercel account | Hosts the web app (swap form + dashboard) | Yes (Hobby) |
| Optional: a Gmail address for the facility (e.g. `shifts@yourfacility.org`) | Sends reminders, receives YES replies | Yes |

---

## 1. Create the rota spreadsheet

**Easiest — use the ready-made workbook:**

1. Download [`sheets/ShiftHub-Rota-Template.xlsx`](../sheets/ShiftHub-Rota-Template.xlsx).
2. In <https://drive.google.com>, click **New → File upload** and select the file.
3. Double-click the uploaded file. If it opens in Office-editing mode, choose
   **File → Save as Google Sheets**. That converted copy is your rota.
4. Rename it `ShiftHub Rota — <facility>`. It already has the five tabs `Rota`, `Settings`,
   `SwapRequests`, `Flags`, `MonthlySummary` with the exact headers.
5. Open the `Settings` tab and edit the values (supervisor email, Telegram chat id, `fromEmail`,
   facility name).

**Or by hand:** <https://sheets.google.com> → **Blank spreadsheet**, then create the five tabs
and copy the headers from [`sheets/README.md`](../sheets/README.md), and import
`sheets/settings.csv` into `Settings`.

Finally, copy the **spreadsheet ID** out of the URL:
`https://docs.google.com/spreadsheets/d/<THIS_PART>/edit` → `<THIS_PART>` is the ID you paste
into every n8n workflow.

---

## 2. Google credentials for n8n

Use **Option A (service account)**. A service account is not another Google login you have to
remember — it is a robot identity that your existing Google account creates, and the sheet is
shared with its email address.

### Option A — Service account (recommended, no expiry)

1. Open <https://console.cloud.google.com> while signed in to the Google account that owns the
   sheet. Create a project (top bar project selector → **New project** → name it `ShiftHub`).
2. **APIs & Services → Library** → search **Google Sheets API** → **Enable**. Then enable
   **Google Drive API** the same way (n8n uses it for the spreadsheet picker).
3. **IAM & Admin → Service Accounts → Create service account** → name it `shifthub-bot` →
   **Create and continue** → skip the optional role screens → **Done**.
4. Open `shifthub-bot` → **Keys → Add key → Create new key → JSON → Create**. A `.json` file
   downloads. Treat it like a password.
5. Run the helper so you can paste the two values n8n needs:

   ```bash
   python3 scripts/google-service-account-key.py /mnt/c/Users/<you>/Downloads/<the-key>.json
   ```

   It prints the service-account email and copies the private key to your Windows clipboard.
6. In the Google Sheet click **Share**, paste the service-account email
   (`...@...iam.gserviceaccount.com`), choose **Editor**, and send.
7. In n8n → **Credentials → Add credential → Google Service Account API**:
   - **Region:** `Global` (the default)
   - **Service Account Email:** the address printed by the helper
   - **Private Key:** paste from the clipboard (Ctrl+V)
   - Save as `ShiftHub Google Sheets`.
8. Select that credential on every **Google Sheets** node in every workflow.

### Option B — OAuth2 (only if you already have a Google OAuth client)

Self-hosted n8n does not ship a Google OAuth client, so this path means creating an OAuth consent
screen and client ID/secret in Google Cloud first. If you already have one: n8n →
**Credentials → New → Google Sheets OAuth2 API** → enter the client details → **Sign in with
Google** → save as `ShiftHub Google Sheets`.

---

## 3. Run n8n locally

### Option A — Node.js (no Docker)

```bash
# check you have Node 20+
node --version

# install n8n globally
npm install -g n8n

# start it (Africa/Lagos keeps the cron times aligned with the rota)
TZ=Africa/Lagos n8n start
```

Open <http://localhost:5678> and create the owner account (email + password). That account is
local to your machine — write it down in your SIWES notes.

**Keep it running after a WSL restart.** A plain `n8n start` dies when WSL or the terminal
closes, which is why the page stops loading. Run this once instead:

```bash
bash scripts/install-n8n-service.sh
```

It installs a systemd user service, starts n8n now, and makes it start automatically whenever
WSL starts. Check it with `systemctl --user status shifthub-n8n`; logs with
`journalctl --user -u shifthub-n8n -f`.

### Option B — Docker

```bash
docker volume create n8n_data
docker run -it --rm --name n8n \
  -p 5678:5678 \
  -e TZ=Africa/Lagos \
  -e GENERIC_TIMEZONE=Africa/Lagos \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n
```

### Give n8n a public address (needed for Telegram + email links)

n8n webhooks are public URLs. On a laptop you can expose them for free with a Cloudflare quick
tunnel:

```bash
# install once: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:5678
```

It prints `https://<random>.trycloudflare.com`. Restart n8n so it uses that URL for webhooks:

```bash
TZ=Africa/Lagos WEBHOOK_URL=https://<random>.trycloudflare.com n8n start
```

(If your n8n version ignores `WEBHOOK_URL`, copy the "Webserver started" URL that n8n prints at
startup and set it in the Settings tab as `publicBaseUrl` instead. The Telegram trigger registers
its webhook with whatever base URL n8n is using — check the **Telegram Trigger** node's
"Test" / production URL in the UI.)

> The tunnel URL changes every time you restart it. Update `publicBaseUrl` in the Settings tab and
> re-register the Telegram webhook after a restart (edit the Telegram Trigger node and save).

---

## 4. Import the workflows

**In the UI:** Workflows → **⋯ → Import from File** → repeat for the 12 files in
`n8n/workflows/`.

**In the CLI** (stop n8n first):

```bash
n8n import:workflow --separate --input=./n8n/workflows
```

Then, for each workflow, open the Google Sheets nodes and set **Document ID** to your
spreadsheet ID (or pick it from the dropdown after authenticating). `PASTE_GOOGLE_SPREADSHEET_ID`
is a deliberate marker — a search for it in the repo finds every place you need to touch.

---

## 5. Credentials

### SMTP (sends every email)

1. Google account → **Security → 2-Step Verification** must be on.
2. <https://myaccount.google.com/apppasswords> → name it `shifthub` → generate a 16-character
   password.
3. n8n → **Credentials → New → SMTP Account**:
   - Host `smtp.gmail.com`, Port `587`, Encryption `STARTTLS`
   - User Name = your facility mailbox, Password = the app password
4. Select it on every **Send Email** node (workflows 01, 02, 03, 06, 07, 08, 09, 12).

### IMAP (watches for "YES" replies) — workflow 06 only

n8n → **Credentials → New → IMAP Account**: Host `imap.gmail.com`, Port `993`, Encryption
`SSL/TLS`, same user + app password. Select it on the **Inbox Trigger** node.

### Telegram (bot for confirmations + alerts)

1. Open Telegram → search **@BotFather** → `/newbot` → name it e.g. `ShiftHub Alerts` → copy the
   **bot token**.
2. n8n → **Credentials → New → Telegram Account** → paste the token → save.
3. Select it on every **Telegram** node and the **Telegram Trigger** node.
4. Get chat ids: message the bot, then message **@userinfobot** (it replies with your numeric id).
   Put the supervisor's id in `Settings → supervisorTelegramChatId` and each staff member's id in
   their `Rota → telegramChatId` cell.
5. Have every staff member press **Start** on the bot once — until they do, Telegram will not
   deliver their messages to the bot.

---

## 6. Settings tab

| key | value |
|---|---|
| `facilityName` | your facility's name |
| `supervisorName` | supervisor's name |
| `supervisorEmail` | where escalations go |
| `supervisorTelegramChatId` | numeric id |
| `fromEmail` | the SMTP mailbox (must match the SMTP user) |
| `publicBaseUrl` | your n8n public URL (tunnel, n8n Cloud, or server) |
| `sendStaffCopies` | `yes` / `no` |
| `timezone` | `Africa/Lagos` |

---

## 7. Publish

n8n 2.x replaced the old **Active** toggle with **Publish**: a workflow runs on its schedule or
serves its webhook only after you publish it. Publish in the order listed in
[`n8n/README.md`](../n8n/README.md).

Then, for each of the other 11 workflows: **⋯ → Settings → Error Workflow → `ShiftHub — 12 ·
Error Notifier`**. A reminder workflow that fails silently is how shifts get missed — this makes
failures loud.

---

## 8. Seed and smoke-test

1. Open **ShiftHub — 10 · Seed Demo Data** → **Execute Workflow**. The `Rota` tab fills with demo
   shifts, including one that starts in ~3 h 10 min with two unconfirmed staff (`SHIFT-DEMO-01`)
   and one that starts in ~2 h 10 min with one staff still to confirm (`SHIFT-DEMO-05`).
2. **Immediately** open **ShiftHub — 03 · 3-Hour Unconfirmed Escalation** → **Execute Workflow**.
   Within a minute the supervisor receives the escalation email and Telegram message. You have
   about 25 minutes of head-room after seeding; if you are later than that, run the seed again.
3. Open **ShiftHub — 02 · 2-Hour Reminders** → **Execute Workflow** → the staff member on
   `SHIFT-DEMO-05` gets the 2-hour nudge.
4. Open **ShiftHub — 09 · Understaffing Check & Flag** → **Execute Workflow**. The `Flags` tab
   gains rows and the supervisor gets the understaffing summary.
5. Open **ShiftHub — 08 · Monthly Hours Summary** → **Execute Workflow**. It reports the
   *previous* month; the seed data includes last-month confirmed shifts so you get a real table.
6. Message the bot `YES` → the rota row flips to `CONFIRMED` (workflow 04).
7. Submit the swap form (next section) → a row appears in `SwapRequests` and the supervisor is
   notified (workflow 07).

---

## 9. Point the deployed web app at your n8n instance

The Vercel project **already exists and is live**:

- **URL:** <https://shifthub-oxunify.vercel.app>
- **Project:** `shifthub` (team `oxunify`), linked to `github.com/unifyWeb3/shifthub` with root
  directory `webapp`, so every push to `main` redeploys it automatically.

All that is left is the one environment variable that tells the app where n8n lives:

1. <https://vercel.com/oxunifyy/shifthub/settings/environment-variables> → add
   - Key: `N8N_WEBHOOK_BASE`
   - Value: your n8n public URL, e.g. `https://abc.trycloudflare.com` — **no trailing slash**
   - Scope: Production (and Preview if you want previews live too)
2. Redeploy: **Deployments → ⋯ → Redeploy** (or push any commit).
3. Open <https://shifthub-oxunify.vercel.app/dashboard> — the amber "Offline preview" banner
   disappears once the proxy reaches n8n.

Until you set it, the site runs in a clearly-labelled offline demo mode (sample rota, swap form
returns a demo reference). Nothing is lost, and nothing pretends to be live.

### If you would rather deploy your own copy

```bash
npm install -g vercel
vercel login
cd webapp
vercel --prod
vercel env add N8N_WEBHOOK_BASE production
```

The routes it serves:

| Route | Purpose |
|---|---|
| `/` | project overview |
| `/swap` | swap request form → `POST /api/swap` → n8n `POST /webhook/swap-request` |
| `/dashboard` | live coverage → `GET /api/dashboard` → n8n `GET /webhook/shifthub-dashboard` |

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Google Sheets node: `401/403` | Credential not authorised, or the service account was not given access to the sheet (Share it with the service-account email). |
| Sheets node returns no rows | The tab name must match exactly (`Rota`, `Settings`, …). |
| Telegram trigger receives nothing | Bot token wrong, staff never pressed **Start**, or n8n's public URL changed after a tunnel restart — re-save the Telegram Trigger node. |
| No email arriving | Gmail app password instead of the account password; check the workflow's **Executions** log for the SMTP error. |
| Duplicate reminders | `reminder1dSent` / `reminder2hSent` cells are empty — the sheet write failed, so the stamp was not saved. Check the Sheets node's output. |
| "no shifts at risk" from workflow 03 | You are more than ~25 minutes after seeding (the demo shift has left the 165–195 minute window) or the row is already confirmed/stamped. Run the seed again, then workflow 03. |
| Cron fires at the wrong hour | The n8n instance timezone is not `Africa/Lagos`: set `TZ=Africa/Lagos` (and `GENERIC_TIMEZONE=Africa/Lagos`) before starting n8n. |
| Confirm link says "invalid" | The token in the email does not match `confirmToken` in the row (re-send reminders after fixing the cell). |
| Dashboard shows "Offline preview" | `N8N_WEBHOOK_BASE` is empty or wrong in Vercel — redeploy after setting it. |
| `403` from the swap form | The n8n webhook path is not `swap-request` (workflow 07) or the workflow is inactive. Webhooks only work on **active** workflows. |

---

## 11. What to show your supervisor

Walk through [`DEMO-GUIDE.md`](DEMO-GUIDE.md) — it is the 10-minute script for the "done when"
criterion: an unconfirmed shift alerts the supervisor at the 3-hour mark.
