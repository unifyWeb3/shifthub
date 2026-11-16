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

> **Use real, deliverable email addresses.** `example.com` is a reserved domain — every mail to
> `anything@example.com` bounces with *"Address not found"*, and no reminder reaches the staff.
> Put a mailbox you can actually open in `supervisorEmail` and `fromEmail`, and put a real address
> in each staff member's `email` column on the `Rota` tab. The demo seed already uses
> `akolaefatoki@gmail.com` for every staff row.

**Or by hand:** <https://sheets.google.com> → **Blank spreadsheet**, then create the five tabs
and copy the headers from [`sheets/README.md`](../sheets/README.md), and import
`sheets/settings.csv` into `Settings`.

Finally, copy the **spreadsheet ID** out of the URL:
`https://docs.google.com/spreadsheets/d/<THIS_PART>/edit` → `<THIS_PART>` is the ID you paste
into every n8n workflow.

---

## 2. Google credentials for n8n

Use **Option A (OAuth2)**. It signs n8n in as your own Google account, so it uses the access the
sheet already has — no robot identity and no key file.

> **If Google says “Service account key creation is disabled”**
> (`iam.disableServiceAccountKeyCreation`), your Google account is under an organization policy
> that blocks service-account keys. That is exactly why Option A exists: OAuth2 is not affected by
> that policy. Use it instead of trying to fight the policy.

### Option A — OAuth2 (recommended, works under org policies)

1. In n8n: **Credentials → Add credential → Google Sheets OAuth2 API**.
2. Copy the **OAuth Redirect URL** shown in the credential window. It is normally
   `http://localhost:5678/rest/oauth2-credential/callback`.
3. In <https://console.cloud.google.com>, signed in to the account that owns the sheet:
   - Create/select a project (top bar → **New project** → `ShiftHub`).
   - **APIs & Services → Library**: enable **Google Sheets API** and **Google Drive API**.
   - **APIs & Services → OAuth consent screen** (newer consoles call it **Google Auth Platform**):
     - App name `ShiftHub`; your email as support and developer contact.
     - User type **External**; add your Google account under **Test users**.
     - **Data Access / Scopes**: add
       `https://www.googleapis.com/auth/spreadsheets`,
       `https://www.googleapis.com/auth/drive.file`, and
       `https://www.googleapis.com/auth/drive.metadata`.
   - **Audience → Test users**: add your own Gmail address. Each project has its own consent
     screen, so a new project needs this repeated — without it Google answers
     *"Access blocked: … has not completed the Google verification process"*.
   - **Credentials → Create credentials → OAuth client ID → Web application**.
     Name it `ShiftHub n8n`; under **Authorized redirect URIs** paste the n8n URL from step 2.
   - Create it, then copy the **Client ID** and **Client secret**.
4. Back in n8n: paste the Client ID and Client secret → **Save** → click
   **Sign in with Google** / **Connect my account** → choose the account that owns the sheet →
   allow the requested access.
   - Typing long secrets is error-prone; this copies each value to the Windows clipboard for you:
     `python3 scripts/oauth-copy.py id` and `python3 scripts/oauth-copy.py secret`.
5. Save the credential as `ShiftHub Google Sheets`, then select it on every **Google Sheets** node.

**Shortcut:** instead of clicking through every Google Sheets node in all 12 workflows, run this
once from the project folder — it attaches the credential and replaces the
`PASTE_GOOGLE_SPREADSHEET_ID` placeholder everywhere in the local n8n instance:

```bash
python3 scripts/wire-credential.py googleSheetsOAuth2Api --spreadsheet-id <SPREADSHEET_ID>
```

The same script wires the other credentials once you have created them:

```bash
python3 scripts/wire-credential.py telegramApi
python3 scripts/wire-credential.py smtp
python3 scripts/wire-credential.py imap
```

Add `--dry-run` first to see what it would change.

**Shortcut for the remaining credentials** — this creates them from the command line (the secret is
prompted for, never echoed or saved) and wires them in one go:

```bash
python3 scripts/add-credential.py telegram   # asks for the @BotFather token
python3 scripts/add-credential.py smtp      # asks for host/user + Google App Password
python3 scripts/add-credential.py imap      # asks for host/user + Google App Password
```

**Shortcut when the app password is already in the instance** — a Google App Password works for
both `imap.gmail.com` and `smtp.gmail.com`, so if the IMAP credential already exists there is no
need to type it again. This reads the app password out of the encrypted IMAP credential in the
local n8n database, creates the SMTP credential from it and wires it in:

```bash
python3 scripts/add-smtp-from-imap.py
```

The secret is never printed, never written to disk and never leaves the machine.

**Expiry note:** while the Google app is in **Testing** mode, Google expires the connection after
7 days. That is fine for the SIWES demo; if you want it to last, open the OAuth consent screen and
**Publish app**. If Google asks for verification, the app still works for your own account behind
an “unverified app” warning — click **Advanced → Go to ShiftHub**.

### Option B — Service account (only if key creation is allowed)

A service account is a robot identity that your Google account creates; the sheet is shared with
its email address. Skip this if you hit the organization-policy error above.

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
   python3 scripts/google-service-account-key.py
   ```

   It finds the newest service-account key in your Downloads folder, prints the
   service-account email, and copies the private key to your Windows clipboard. If it picks the
   wrong file, pass the exact path as an argument.
6. In the Google Sheet click **Share**, paste the service-account email
   (`...@...iam.gserviceaccount.com`), choose **Editor**, and send.
7. In n8n → **Credentials → Add credential → Google Service Account API**:
   - **Region:** `Global` (the default)
   - **Service Account Email:** the address printed by the helper
   - **Private Key:** paste from the clipboard (Ctrl+V)
   - Save as `ShiftHub Google Sheets`.
8. Select that credential on every **Google Sheets** node in every workflow.

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

It prints `https://<random>.trycloudflare.com`. n8n needs that URL in two places:

| variable | meaning |
|---|---|
| `N8N_WEBHOOK_URL` | base URL for **both** test and production webhooks (n8n 2.x) |
| `N8N_EDITOR_BASE_URL` | the URL you open in the browser — keep it `http://localhost:5678` |

> Keep `N8N_EDITOR_BASE_URL=http://localhost:5678`. The n8n session cookie is host-only and
> Google's OAuth redirect URI is `http://localhost:5678/rest/oauth2-credential/callback`, so
> opening the UI through the tunnel breaks the Google sign-in.

If n8n runs as the systemd user service (`shifthub-n8n.service`), put the tunnel URL in the unit
file and restart:

```bash
sudo systemctl --user daemon-reload
sudo systemctl --user restart shifthub-n8n
```

**Do not hand-edit that URL after every tunnel restart.** One script keeps every copy in sync
(systemd unit → `Settings.publicBaseUrl` in the sheet → workflow 13 → `webapp/n8n-url.txt`):

```bash
python3 scripts/sync-tunnel-url.py --publish
```

It reads the live URL from the tunnel log, rewrites the unit, restarts n8n, patches and runs
**ShiftHub — 13 · Maintenance: Set Public Base URL** (which writes `publicBaseUrl` back into the
`Settings` tab), and writes the URL to `webapp/n8n-url.txt`. With `--publish` it also commits and
pushes that file, so the deployed web app picks the new URL up (a push triggers the Vercel
redeploy).

> The tunnel URL changes every time you restart it. After a tunnel restart run
> `python3 scripts/sync-tunnel-url.py --publish` — otherwise the web app still points at the dead
> URL. The Telegram trigger re-registers itself with the new base URL when n8n restarts.

---

## 4. Import the workflows

**In the UI:** Workflows → **⋯ → Import from File** → repeat for the 13 files in
`n8n/workflows/` (01–12 are the functional workflows, 13 is the maintenance workflow).

**In the CLI** (stop n8n first):

```bash
n8n import:workflow --separate --input=./n8n/workflows
```

Then, for each workflow, open the Google Sheets nodes and set **Document ID** to your
spreadsheet ID (or pick it from the dropdown after authenticating). `PASTE_GOOGLE_SPREADSHEET_ID`
is a deliberate marker — a search for it in the repo finds every place you need to touch.

The spreadsheet id can also be filled in from the CLI, together with the Google credential:

```bash
python3 scripts/wire-credential.py googleSheetsOAuth2Api \
  --spreadsheet-id 1eHo1kIBUcAnAwP-joLm6RFe7cpcD6wz18FJtHIZfzRw
```

### The public webhooks (short paths)

The three HTTP entry points are deliberately short and stable:

| URL | Used by |
|---|---|
| `GET  /webhook/shifthub-dashboard` | the Vercel dashboard (`/api/dashboard`) |
| `POST /webhook/swap-request` | the Vercel swap form (`/api/swap`) |
| `GET  /webhook/confirm-shift?token=…` | the one-tap link inside every reminder e-mail |

In n8n 2.x a Webhook node without a `webhookId` is served from
`/webhook/<workflowId>/<lowercased node name>/<path>`, which breaks as soon as the node name
contains a space. Every webhook node in `n8n/workflows/` therefore carries an explicit
`webhookId` (`shifthub-dashboard`, `swap-request`, `confirm-shift`). If you re-import the
workflows into a fresh instance and the paths look wrong, run:

```bash
python3 scripts/sync-webhook-paths.py --force
```

---

## 5. Credentials

The quickest way (no clicking through the n8n UI, and the secret is never typed into a web form
or written to disk):

```bash
python3 scripts/add-credential.py telegram   # asks for the BotFather token (not echoed)
python3 scripts/add-credential.py smtp       # host/port/user + the 16-character app password
python3 scripts/add-credential.py imap       # host/port/user + the same app password
```

Each script creates the credential in the local n8n instance, wires it into every matching node
and re-publishes the drafts, so the running workflows carry it. Check the result with:

```bash
python3 scripts/check-status.py
```

It prints, per workflow, whether it is published, whether every trigger activated (a missing
credential shows up here), the registered webhook paths and the next cron run.

The same thing by hand:

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

From the CLI, publishing one workflow is:

```bash
n8n publish:workflow --id=<workflowId>
```

and publishing **every** workflow in one pass (this re-snapshots the current draft — including
the credentials and the spreadsheet id — as the published version, which is what n8n actually
runs) is:

```bash
python3 scripts/publish-drafts.py
```

> n8n runs the *published snapshot*, not the draft you see in the editor. If you wire a
> credential in the UI and the workflow still says "Node does not have any credentials set",
> publish it again (or run `scripts/publish-drafts.py`).

Then, for each of the other 11 workflows: **⋯ → Settings → Error Workflow → `ShiftHub — 12 ·
Error Notifier`**. A reminder workflow that fails silently is how shifts get missed — this makes
failures loud.

---

## 8. Seed and smoke-test

1. Open **ShiftHub — 10 · Seed Demo Data** → **Execute Workflow**. The `Rota` tab is cleared and
   refilled with demo shifts, including one that starts in ~3 h 10 min with two unconfirmed staff
   (`SHIFT-DEMO-01`) and one that starts in ~2 h 10 min with one staff still to confirm
   (`SHIFT-DEMO-05`). Re-running it is safe: it clears the tab first, so you never get duplicate
   rows.
2. **Immediately** open **ShiftHub — 03 · 3-Hour Unconfirmed Escalation** → **Execute Workflow**.
   Within a minute the supervisor receives the escalation email *and* Telegram message. You have
   about 25 minutes of head-room after seeding; if you are later than that, run the seed again.

   > Workflow 03 starts with a **Cron trigger**, so `n8n execute --id …` cannot start it from the
   > CLI (the CLI only starts Manual / Execute-Workflow triggers). Either use **Execute Workflow**
   > in the editor as above, or simply wait for the next 15-minute cron tick — the cron runs the
   > **published** version, which is exactly what production runs.
3. Open **ShiftHub — 02 · 2-Hour Reminders** → **Execute Workflow** → the staff member on
   `SHIFT-DEMO-05` gets the 2-hour nudge.
4. Open **ShiftHub — 09 · Understaffing Check & Flag** → **Execute Workflow**. The `Flags` tab
   gains rows and the supervisor gets the understaffing summary.
5. Open **ShiftHub — 08 · Monthly Hours Summary** → **Execute Workflow**. It reports the
   *previous* month; the seed data includes last-month confirmed shifts so you get a real table.
6. Message the bot `YES` → the rota row flips to `CONFIRMED` (workflow 04).
7. Submit the swap form (next section) → a row appears in `SwapRequests` and the supervisor is
   notified (workflow 07).

### Checking what n8n is really running

n8n runs the **published snapshot**, not the draft in the editor. To see the published nodes,
their credentials and their connections:

```bash
python3 scripts/show-published.py XxrIxUoM1XL25Aqd   # workflow 03
```

If a credential is missing there, re-publish: `python3 scripts/publish-drafts.py`.

---

## 9. Point the deployed web app at your n8n instance

The Vercel project **already exists and is live**:

- **URL:** <https://shifthub-oxunify.vercel.app>
- **Project:** `shifthub` (team `oxunify`), linked to `github.com/unifyWeb3/shifthub` with root
  directory `webapp`, so every push to `main` redeploys it automatically.

### The URL lives in the repo, not in an environment variable

A Cloudflare quick tunnel gets a **new random hostname every time it restarts**. If that URL were
baked into a Vercel environment variable, the web app would break (and need a redeploy) on every
tunnel restart. So the URL is kept in one file in the repo:

```
webapp/n8n-url.txt     ->  https://<current-tunnel>.trycloudflare.com
```

`webapp/api/_n8n-base.js` reads that file **at request time** from the GitHub raw URL and uses it
as the n8n base URL (falling back to the `N8N_WEBHOOK_BASE` environment variable, then to a
clearly-labelled offline demo). `scripts/sync-tunnel-url.py --publish` writes the file and pushes
it. A git push is enough — no Vercel redeploy, no console clicking.

If you prefer an environment variable instead, it still works:

1. <https://vercel.com/oxunifyy/shifthub/settings/environment-variables> → add
   - Key: `N8N_WEBHOOK_BASE`
   - Value: your n8n public URL, e.g. `https://abc.trycloudflare.com` — **no trailing slash**
   - Scope: Production (and Preview if you want previews live too)
2. Redeploy: **Deployments → ⋯ → Redeploy** (or push any commit).
3. Open <https://shifthub-oxunify.vercel.app/dashboard> — the amber "Offline preview" banner
   disappears once the proxy reaches n8n.

Until it can reach n8n, the site runs in a clearly-labelled offline demo mode (sample rota, swap
form returns a demo reference). Nothing is lost, and nothing pretends to be live.

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
| Google sign-in says *"Access blocked: … has not completed the Google verification process"* | The OAuth app is in **Testing** mode and your email is not an approved tester. Google Auth Platform → **Audience → Test users → Add** → add your own Gmail. Every new project/client needs its own test user and scopes. |
| Google sign-in says *"Client authentication failed"* | The Client ID and Client Secret in n8n are not from the same OAuth client, or the client was deleted/rotated. Re-download the client's JSON and copy both values from it (`python3 scripts/oauth-copy.py id` / `secret`). |
| Google Sheets node: `401/403` | Credential not authorised, or the service account was not given access to the sheet (Share it with the service-account email). |
| Sheets node returns no rows | The tab name must match exactly (`Rota`, `Settings`, …). |
| Telegram trigger receives nothing | Bot token wrong, staff never pressed **Start**, or n8n's public URL changed after a tunnel restart — re-save the Telegram Trigger node. |
| No email arriving | Gmail app password instead of the account password; check the workflow's **Executions** log for the SMTP error. |
| Duplicate reminders | `reminder1dSent` / `reminder2hSent` cells are empty — the sheet write failed, so the stamp was not saved. Check the Sheets node's output. |
| "no shifts at risk" from workflow 03 | You are more than ~25 minutes after seeding (the demo shift has left the 165–195 minute window) or the row is already confirmed/stamped. Run the seed again, then workflow 03. |
| Cron fires at the wrong hour | The n8n instance timezone is not `Africa/Lagos`: set `TZ=Africa/Lagos` (and `GENERIC_TIMEZONE=Africa/Lagos`) before starting n8n. |
| Confirm link says "invalid" | The token in the email does not match `confirmToken` in the row (re-send reminders after fixing the cell). |
| Dashboard shows "Offline preview" | The web app could not resolve the n8n URL — `webapp/n8n-url.txt` is stale. Run `python3 scripts/sync-tunnel-url.py --publish` (it rewrites the file and pushes it). If you use the environment variable instead, it must be set **and** the app redeployed. |
| `403` from the swap form | The n8n webhook path is not `swap-request` (workflow 07) or the workflow is inactive. Webhooks only work on **active** workflows. |
| `404 … is not registered` from a webhook URL | The workflow is not published, or the path is the old long form (`/webhook/<workflowId>/dashboard webhook/…`). Run `python3 scripts/sync-webhook-paths.py --force`, publish, and use the short path `/webhook/shifthub-dashboard`. |
| Workflow says "Node does not have any credentials set" | The workflow is running its **published snapshot**, which was taken before you wired the credential. Publish it again (`n8n publish:workflow --id=<id>` or `python3 scripts/publish-drafts.py`). |
| Everything works locally but the Vercel app says "Offline preview" | The tunnel URL changed (quick tunnels change on every restart) or the file was not pushed. Run `python3 scripts/sync-tunnel-url.py --publish`, then wait for the Vercel redeploy. |

---

## 11. What to show your supervisor

Walk through [`DEMO-GUIDE.md`](DEMO-GUIDE.md) — it is the 10-minute script for the "done when"
criterion: an unconfirmed shift alerts the supervisor at the 3-hour mark.
