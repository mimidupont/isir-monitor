# ISIR Monitor

Monitors an insolvency case on isir.justice.cz and sends an email alert
whenever new rows appear in any of the 5 tabs. Runs daily for free via
GitHub Actions — no laptop or server needed.

---

## Setup (one-time, ~10 minutes)

### 1. Create a GitHub account
Go to https://github.com and sign up if you don't have an account.

### 2. Create a new repository
- Click the **+** icon (top right) → **New repository**
- Name it `isir-monitor`
- Set it to **Private** (so your snapshot data isn't public)
- Click **Create repository**

### 3. Upload the files
Upload these two files to the repository root:
- `isir_monitor.py`
- `.github/workflows/monitor.yml`  ← make sure the folder structure is kept

You can drag and drop them in the GitHub web interface, or use Git.

### 4. Get a Gmail App Password
a) Go to https://myaccount.google.com/security  
b) Make sure **2-Step Verification** is ON  
c) Go to https://myaccount.google.com/apppasswords  
d) Create one called "ISIR Monitor"  
e) Copy the 16-character password (you'll need it in the next step)

### 5. Add your credentials as GitHub Secrets
In your repository, go to:
**Settings → Secrets and variables → Actions → New repository secret**

Add these three secrets one by one:

| Name | Value |
|------|-------|
| `EMAIL_SENDER` | your Gmail address (e.g. you@gmail.com) |
| `EMAIL_PASSWORD` | the 16-char App Password from step 4 |
| `EMAIL_RECIPIENT` | where to send alerts (can be the same Gmail) |

### 6. Trigger the first run manually (creates the baseline snapshot)
- Go to the **Actions** tab in your repository
- Click **ISIR Daily Monitor** in the left sidebar
- Click **Run workflow** → **Run workflow**
- Wait ~30 seconds for it to finish
- You should see a green checkmark
- No email is sent on the first run — it just saves the current state

### 7. Done!
From now on the script runs automatically every day at 08:00 UTC.
If anything new appears in the case, you'll get an email.

---

## How it works

1. GitHub's servers run `isir_monitor.py` every morning
2. The script fetches all 5 tabs of the insolvency case
3. It compares the current data to `isir_snapshot.json` (stored in this repo)
4. If any new rows are found, it sends you an email with the new content
5. The updated snapshot is committed back to the repo automatically

## Changing the schedule
Edit the `cron` line in `.github/workflows/monitor.yml`.
Format: `minute hour * * *` (times are in UTC, which is Vienna -1h in winter, -2h in summer).

Examples:
- `0 8 * * *`  → 08:00 UTC = 09:00 Vienna (winter) / 10:00 (summer)
- `0 6 * * *`  → 06:00 UTC = 07:00 Vienna (winter)
- `0 8 * * 1-5` → weekdays only
