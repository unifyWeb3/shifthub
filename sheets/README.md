# Google Sheets templates

ShiftHub uses one spreadsheet with five tabs. Create it manually (fastest) or import the CSVs in
this folder.

## Tabs and exact headers

**1. `Rota`** — one row per *assignment* (a staff member booked on a shift).
Required headers, in this order:

```
shiftId,date,startTime,endTime,ward,role,requiredCount,staffId,staffName,email,telegramChatId,assignmentId,status,confirmToken,reminder1dSent,reminder2hSent,escalation3hSent,understaffedFlag
```

| Column | Meaning | Example |
|---|---|---|
| `shiftId` | Shift identifier, shared by every row of the same shift | `SHIFT-2026-0042` |
| `date` | `YYYY-MM-DD` | `2026-11-05` |
| `startTime` / `endTime` | `HH:MM`, 24h. If the end time is earlier than the start time the shift is overnight | `19:00` / `07:00` |
| `ward` | Unit / ward | `ICU` |
| `role` | Role required | `Nurse` |
| `requiredCount` | How many staff must be confirmed for this shift (same value on every row of the shift) | `2` |
| `staffId` / `staffName` | Staff identity | `STF-001`, `Adaeze Nnamdi` |
| `email` | Used for reminders + YES-by-email | `adaeze.nnamdi@example.com` |
| `telegramChatId` | Numeric Telegram chat id (get it from @userinfobot) | `100000001` |
| `assignmentId` | Unique row id — the update key for every write. Must be unique in the sheet: the workflows match on it when they stamp a row. | `ASG-K3F9A2-1001` |
| `status` | `PENDING`, `CONFIRMED`, `DECLINED` or `SWAPPED` | `PENDING` |
| `confirmToken` | Random token used by the one-tap email confirmation link | `tok-a1b2c3d4` |
| `reminder1dSent` | Timestamp of the T-1 day reminder | `2026-11-04T18:00:05` |
| `reminder2hSent` | Timestamp of the T-2 hour reminder | `2026-11-05T05:00:00` |
| `escalation3hSent` | Timestamp of the supervisor escalation | `2026-11-05T04:00:00` |
| `understaffedFlag` | `YES` when the shift is below required headcount | `YES` |

**2. `Settings`** — two columns, `key` and `value`. Rows:

| key | value | notes |
|---|---|---|
| `facilityName` | `Federal Medical Centre` | used in every message |
| `supervisorName` | `Dr. A. Supervisor` | |
| `supervisorEmail` | `supervisor@example.com` | receives escalations, flags, monthly report |
| `supervisorTelegramChatId` | `100000000` | numeric chat id |
| `fromEmail` | `shifthub@example.com` | the SMTP account the mails are sent from |
| `publicBaseUrl` | `http://localhost:5678` | base URL for confirmation links; use your public n8n URL in production |
| `sendStaffCopies` | `yes` | `no` stops the per-staff monthly email |
| `timezone` | `Africa/Lagos` | must match the n8n instance timezone |

**3. `SwapRequests`** — `requestId,createdAt,assignmentId,shiftId,date,startTime,endTime,ward,role,requestorName,requestorContact,targetPreference,reason,status`

**4. `Flags`** — `flaggedAt,shiftId,date,startTime,ward,role,requiredCount,confirmedCount,missingCount,message`

**5. `MonthlySummary`** — `month,staffId,staffName,shiftsConfirmed,hoursWorked,generatedAt`

## Files here

| File | Use |
|---|---|
| `settings.csv` | Import into the `Settings` tab, then edit the values |
| `rota-example.csv` | 12 worked example rows — copy them into `Rota` to see the shape, or ignore them and use workflow 10 to seed demo data with today's dates. The seed adds a short run tag to every `assignmentId` so that re-seeding never creates two rows with the same key. |
| `swap-requests-headers.csv`, `flags-headers.csv`, `monthly-summary-headers.csv` | Header-only imports for the three write tabs |

## Importing a CSV into a tab

1. Create the spreadsheet in Google Sheets.
2. Create a tab, rename it exactly as above.
3. **File → Import → Upload** the CSV, or paste the header row into row 1 and the data below it.
4. Column order must match the headers above — the workflows write by column name, but the seed
   workflow appends by header match, so keep them identical.

## Test your sheet before wiring n8n

Add one row manually:

```
shiftId: TEST-1
date: 2026-11-05
startTime: 07:00
endTime: 19:00
ward: Ward A
role: Nurse
requiredCount: 1
staffId: STF-TEST
staffName: Test Nurse
email: you@example.com
telegramChatId: 100000001
assignmentId: ASG-TEST-1
status: PENDING
confirmToken: test-token-1
```

Then run workflow **10 · Seed Demo Data** or **01 · Daily Reminders** and check that the row's
`reminder1dSent` cell gets a timestamp.
