# Noindex Monitor - Render MVP Deployment

Deploy to Render's free tier in ~30 minutes. No server, no Cam needed.

---

## How It Works

- Reads the Master SEO Matrix (hyperlinks in column A identify clients + link to their matrix)
- Opens tab 1 of each client matrix, extracts URLs from every hyperlinked cell
- Plain-text cells (draft/proposed pages) are ignored
- Scans each URL for noindex (meta robots + X-Robots-Tag header)
- Compares to yesterday's state, flags NEW noindexes
- Posts daily Slack alert highlighting new issues separately from ongoing ones
- Dashboard shows per-client pass/fail, URL-level detail, allowlist, CSV export

---

## Part 1 - Google Service Account (10 min)

### 1.1 Create the project

1. <https://console.cloud.google.com/>
2. Top bar > project selector > **New Project**
3. Name: `Monochrome Noindex Monitor` > Create

### 1.2 Enable Sheets API

1. Left sidebar > **APIs & Services** > **Library**
2. Search "Google Sheets API" > **Enable**

### 1.3 Create service account

1. Left sidebar > **IAM & Admin** > **Service Accounts** > **Create Service Account**
2. Name: `noindex-monitor` > Create and Continue > skip role > Done
3. Click the service account > **Keys** tab > **Add Key** > **Create new key** > **JSON** > Create
4. JSON file downloads - rename to `service_account.json`

### 1.4 Share sheets with the service account

Open `service_account.json`, find `client_email` (looks like `noindex-monitor@...iam.gserviceaccount.com`).

Share with that email (Viewer access):
- Master SEO Matrix
- Every individual client matrix linked from column A

**Shortcut**: if all client matrices are in one Drive folder, share the folder once.

---

## Part 2 - Slack Webhook (3 min)

1. <https://api.slack.com/apps> > **Create New App** > **From scratch**
2. Name: `Noindex Monitor`, select your workspace
3. **Incoming Webhooks** > toggle On
4. **Add New Webhook to Workspace** > select channel (e.g. `#seo-alerts`)
5. Copy the webhook URL

---

## Part 3 - GitHub Repo (5 min)

Render deploys from GitHub, so the code needs to be in a repo.

### 3.1 Create a free GitHub account

If you don't have one: <https://github.com/signup>

### 3.2 Create a new private repo

1. <https://github.com/new>
2. Name: `noindex-monitor`
3. Visibility: **Private**
4. Check "Add a README file"
5. Click Create

### 3.3 Upload project files

Easiest method - web upload:

1. In the new repo, click **Add file** > **Upload files**
2. Drag every file from the noindex-monitor folder (except `service_account.json` - that stays OFF GitHub)
3. Make sure `.gitignore` is included (it prevents accidentally committing secrets)
4. Commit message: "Initial upload"
5. Click **Commit changes**

**Do NOT upload `service_account.json` to GitHub.** It's a credential. The `.gitignore` file prevents this automatically if you use git CLI, but when uploading via web you need to be careful.

---

## Part 4 - Render Deployment (12 min)

### 4.1 Sign up

<https://render.com> > Sign up with GitHub > authorize Render to see your repos.

### 4.2 Create a Blueprint (deploys both web app + cron at once)

1. Dashboard > **New** > **Blueprint**
2. Connect your `noindex-monitor` repo
3. Render reads `render.yaml` and proposes two services: web app + cron
4. Click **Apply**

### 4.3 Add the secret service account file

Render can't pull your `service_account.json` from GitHub (and shouldn't). Instead:

1. In Render dashboard, click your **noindex-monitor** web service
2. Left sidebar > **Environment**
3. Scroll to **Secret Files**
4. **Add Secret File**
   - Filename: `service_account.json`
   - Contents: paste the entire JSON from your downloaded file
5. Save

6. Repeat for the **noindex-daily-scan** cron service (same secret file)

### 4.4 Fill in environment variables

For BOTH services (web + cron), set these env vars:

| Key | Value |
|---|---|
| `GOOGLE_SHEET_ID` | `1R0w3whcvz9ciarU_lEzXH9OotNhyyrI60ohUPRBikts` |
| `SLACK_WEBHOOK_URL` | your webhook from Part 2 |
| `APP_URL` | `https://noindex-monitor.onrender.com` (filled after first deploy) |

### 4.5 Trigger the deploy

Render auto-deploys when you apply the blueprint. Wait ~5 min. Check logs.

### 4.6 Get your URL

Once deployed, your dashboard lives at something like:
```
https://noindex-monitor.onrender.com
```

Update `APP_URL` env var to this exact URL. Restart service.

---

## Part 5 - First Run (30-60 min)

1. Open `https://noindex-monitor.onrender.com`
2. Click **Sync Sheet** - reads master + all client matrices. Takes a few minutes.
3. Click **Run Full Scan** - checks every URL. Takes 20-60 min depending on total URL count.
4. Check Slack for the summary post.

The daily cron runs at 7am server time (14:00 UTC - set in `render.yaml`). Adjust schedule in `render.yaml` if needed and commit the change to GitHub; Render auto-deploys.

---

## Day-to-Day

- **Active client URLs**: hyperlinked cells in tab 1 of their matrix get checked
- **Draft/proposed pages**: plain text in tab 1 = ignored (only hyperlinked pages go live)
- **Add a client**: add a hyperlinked row to master matrix column A above "Retired Clients"
- **Retire a client**: move them below "Retired Clients" row
- **Allowlist known noindexes**: click a client > Manage Allowlist > paste URL
- **New noindex alerts**: Slack only alerts on URLs that became noindexed since last scan
- **Export a report**: client page > Export CSV

---

## How The Delta Detection Works

The accuracy angle you wanted:

```
URL state stored: {is_noindex, previous_noindex, first_noindex_detected}

Scan Day 1:
  URL checks as noindex → is_noindex=True, previous=False → NEW
  Slack: "🚨 New noindex: /thank-you/"

Scan Day 2 (no change):
  URL still noindex → is_noindex=True, previous=True → NOT NEW
  Slack: included in "Ongoing (already flagged)"

Scan Day 3 (fixed):
  URL now pass → is_noindex=False, first_detected cleared
  If it ever re-appears, counts as NEW again
```

So Slack only pings you about actionable changes. Recurring noindexes you've already acknowledged (or allowlisted) stay quiet.

---

## Troubleshooting

**Deploy fails with "ModuleNotFoundError: No module named X"**
- `requirements.txt` missing a dep. Add it, commit to GitHub, auto-redeploys.

**"Master sheet error: the caller does not have permission"**
- Service account email not shared on the Master SEO Matrix.

**"[Client]: the caller does not have permission"**
- That specific client matrix isn't shared with the service account.

**"[Client]: no hyperlinked URLs in tab 1"**
- Tab 1 of that client's matrix has no hyperlinked cells. Either their URLs aren't hyperlinked yet, or their tab 1 is a different structure.

**Dashboard loads slow first time each morning**
- Render's free tier sleeps after 15 min of inactivity. First hit wakes it (~30 sec). Paid tier ($7/mo) removes sleep.

**Cron didn't run**
- Render dashboard > noindex-daily-scan service > check Logs tab.

---

## Moving to cPanel Later

When you want to move this to Cam's server:
1. Export `noindex.db` from Render's disk (or start fresh)
2. Copy entire repo to cPanel
3. Upload `service_account.json` via File Manager
4. Set env vars in cPanel's Python App UI
5. Set up cron job
6. Update DNS to point `noindex.monochromemktg.com` to cPanel
7. Turn off Render service

Code is identical across both hosts. See separate cPanel guide when ready.

---

## File Reference

```
noindex-monitor/
  app.py              # Flask app + API routes
  database.py         # SQLAlchemy models with delta tracking
  scanner.py          # URL checking (meta + X-Robots-Tag, delta detection)
  sheets.py           # Master matrix + hyperlink-aware client matrix reader
  slack_notify.py     # Slack formatter (NEW vs ongoing)
  cron_scan.py        # Daily cron entry point
  wsgi.py             # WSGI entry for gunicorn
  Procfile            # Render process definition
  render.yaml         # Render blueprint (auto-deploys web + cron)
  requirements.txt    # Python deps
  .env.example        # Local dev config template
  .gitignore          # Keeps secrets out of git
  templates/
    dashboard.html
    client_detail.html
  static/
    css/style.css
    js/dashboard.js
    js/client_detail.js
```
