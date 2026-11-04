# Demo guide — the 10-minute ShiftHub walkthrough

This is the script to show your supervisor. It ends with the "done when" criterion:
**an unconfirmed shift alerts the supervisor at the 3-hour mark.**

## Before the demo (15 minutes, once)

1. n8n running, all 12 workflows imported, credentials connected, workflows **active**.
2. `Settings` tab filled in (especially `supervisorEmail`, `supervisorTelegramChatId`, `fromEmail`).
3. Vercel app deployed, `N8N_WEBHOOK_BASE` set to your n8n public URL.
4. Telegram: your supervisor has pressed **Start** on the bot; you know their chat id.
5. Run **10 · Seed Demo Data** once (clears nothing — delete the `Rota` rows first if you are
   re-seeding, otherwise you get duplicates).
6. Have your phone ready with the supervisor's Telegram chat open and the Gmail inbox open.

---

## Minute 0–2 · The problem (1 slide, 20 seconds of talking)

> "A shift is uncovered because nobody reminded the right person, nobody knew they hadn't
> confirmed, and the swap happened in a WhatsApp group with no record. ShiftHub fixes all three
> with one rota sheet and twelve n8n workflows."

Open the **Overview** page on the deployed site. Point at the 3-hour escalation step.

---

## Minute 2–5 · The rota and the reminders

1. Open the Google Sheet → `Rota` tab. Show the columns: `requiredCount`, `status`,
   `confirmToken`, and the three reminder stamps.
2. In n8n, open **01 · Daily 6PM Reminders**. Point at the cron (`0 18 * * *`) and the filter
   *"date == tomorrow AND status == PENDING AND not already reminded"*.
3. Show the seeded row for tomorrow (`SHIFT-DEMO-02`, Fatima Bello, PENDING).
4. **Execute** the workflow. Within seconds:
   - the supervisor's phone buzzes with the Telegram reminder,
   - the staff email arrives,
   - the rota cell `reminder1dSent` now has a timestamp.
5. Say: *"At 2 hours before the shift, workflow 02 sends the final nudge — same logic, 15-minute
   check."*

---

## Minute 5–7 · YES to confirm (all three ways)

1. **Telegram:** message the bot `YES`. The bot replies with the confirmed shift, and the rota row
   flips to `CONFIRMED` (workflow 04).
2. **Email reply:** reply `YES` to the reminder email. Within a minute the staff gets a reply
   email and the rota updates (workflow 06, IMAP).
3. **One-tap link:** open the reminder email on the phone and tap the confirmation link
   (workflow 05). It returns a plain-text confirmation page.
4. Say: *"No app, no portal — staff answer the same way they already talk."*

---

## Minute 7–9 · THE HEADLINE: unconfirmed at the 3-hour mark

1. Open the `Rota` tab and show `SHIFT-DEMO-01` — **today**, ICU, starts in ~3 hours,
   `requiredCount = 2`, both assignments still `PENDING`.
2. Open **03 · 3-Hour Unconfirmed Escalation** and point at the code: it selects PENDING
   assignments whose start time is 165–195 minutes away (the 15-minute cron means the window is
   ±15 min) and skips anything already stamped in `escalation3hSent`.
3. **Execute the workflow.**
4. Within seconds the supervisor receives:
   - an email titled `[ShiftHub] ALERT: 2 unconfirmed shift(s) at the 3-hour mark`, listing
     Ngozi Eze and Kemi Adeyemi, the ward, role, shift times and "starts in ~180 min",
   - the same message on Telegram.
5. Show the rota: `escalation3hSent` now has a timestamp, so the alert fires **once**, not every
   15 minutes.
6. Confirm it in the dashboard: the **red banner** appears —
   *"2 shift(s) start within ~3 hours and are UNCONFIRMED"* — and the supervisor alert is the
   documented action.
7. Say: *"This is the done-when criterion: the alert fires before the ward opens, and the system
   stops nagging once someone confirms."*

---

## Minute 9–10 · Swaps, flags and hours

1. Open `/swap` on the deployed site, submit a request as a staff member. Show the reference ID
   (SWP-…), the new row in the `SwapRequests` tab and the supervisor notification.
2. Open `/dashboard` — coverage %, pending confirmations, understaffed shifts with red rows, and
   the progress bars per shift.
3. Run **09 · Understaffing Check & Flag** → `Flags` tab gains a row; the supervisor gets the
   "understaffed shifts" summary.
4. Run **08 · Monthly Hours Summary** → the supervisor gets the table (previous month, confirmed
   hours per staff, overnight shifts counted correctly) and `MonthlySummary` fills up.
5. Close on: *"Every number in that dashboard comes from one Google Sheet, every action from n8n,
   and nothing was typed twice."*

---

## If something fails during the demo

| Problem | 30-second fix |
|---|---|
| Telegram message didn't arrive | Bot token / user didn't press Start → fall back to showing the email, then re-run the workflow after they press Start. |
| No email | Check the workflow's Executions log for the SMTP error; usually the app password expired. |
| The escalation says "no shifts at risk" | You re-seeded after the shift time passed, or the row is `CONFIRMED`. Run the seed again (new row starts in ~3h) and execute workflow 03 again. |
| Dashboard says "Offline preview" | `N8N_WEBHOOK_BASE` unset in Vercel → set it and redeploy, or demo the workflow JSON instead. |

## Screenshots worth taking for your SIWES report

1. The n8n canvas of workflow 03 (with the sticky note visible).
2. The rota sheet showing `escalation3hSent` filled in.
3. The supervisor email + Telegram alert.
4. The dashboard with the red 3-hour banner.
5. The swap form with its SWP reference.
6. The monthly hours table.
