# NI DVA Driving Test Slot Checker

Automated system that monitors the NI DVA booking website for available driving test slots at **Hydebank** and **Balmoral** test centres. Sends WhatsApp notifications via Twilio when slots are found — or confirms "NO SLOTS" each check so you know it's running.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        GITHUB ACTIONS                             │
│                                                                   │
│   ┌─────────────┐     ┌──────────────┐     ┌────────────────┐   │
│   │  Cron        │────▶│  checker.py  │────▶│  DVA Booking   │   │
│   │  Schedule    │     │              │     │  Website       │   │
│   │  (every 25m) │     │  - Submits   │     │  (nidirect)    │   │
│   └─────────────┘     │    licence   │     └───────┬────────┘   │
│                        │  - Parses    │             │             │
│                        │    response  │◀────────────┘             │
│                        └──────┬───────┘                           │
│                               │                                   │
│                    ┌──────────┴──────────┐                       │
│                    │                     │                        │
│              SLOTS FOUND            NO SLOTS                     │
│                    │                     │                        │
│                    ▼                     ▼                        │
│   ┌─────────────────────┐  ┌─────────────────────┐              │
│   │  WhatsApp Alert     │  │  WhatsApp Status    │              │
│   │  "SLOT FOUND!       │  │  "NO SLOTS          │              │
│   │   Book NOW!"        │  │   Next check 25min" │              │
│   └─────────┬───────────┘  └─────────┬───────────┘              │
└─────────────┼─────────────────────────┼──────────────────────────┘
              │                         │
              ▼                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                     TWILIO API                                    │
│            WhatsApp Business Sandbox                              │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  YOUR PHONE     │
              │  (WhatsApp)     │
              │                 │
              │  You book       │
              │  manually on    │
              │  DVA website    │
              └─────────────────┘
```

---

## How It Works

```
1. GitHub Actions fires every 25 minutes (Mon-Sat, 7am-5pm UK)
         │
         ▼
2. checker.py loads your credentials from GitHub Secrets
         │
         ▼
3. Connects to DVA booking site with your licence number
         │
         ▼
4. Searches for available slots at HYDEBANK & BALMORAL
         │
         ├── FOUND ──▶ WhatsApp: "SLOT FOUND! Book NOW!" + link
         │
         └── NONE ───▶ WhatsApp: "NO SLOTS. Next check in 25 min."
```

---

## Setup Instructions

### Step 1: Clone the repo

```bash
git clone https://github.com/avraaws2022/nidriving.git
cd nidriving
```

### Step 2: Set up Twilio (WhatsApp notifications)

1. Sign up at https://www.twilio.com/try-twilio (free trial)
2. Go to **Messaging > Try it out > Send a WhatsApp message**
3. Follow the instructions to join the sandbox (send a code to +1 415 523 8886)
4. Note your:
   - **Account SID** (starts with `AC...`)
   - **Auth Token**
   - The sandbox **From number** is `whatsapp:+14155238886`

### Step 3: Add GitHub Secrets

Go to: https://github.com/avraaws2022/nidriving/settings/secrets/actions

Add these secrets:

| Secret Name | Value | Example |
|-------------|-------|---------|
| `DVA_LICENCE_NUMBER` | Your 8-digit NI licence number | `42704812` |
| `DVA_DOB` | Date of birth (DD/MM/YYYY) | `01/01/1990` |
| `DVA_THEORY_CERT` | Theory test certificate number | `TC123456` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `AC0b7e15...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `5ca443b6...` |
| `WHATSAPP_TO_NUMBER` | Your phone with country code | `+XXXXXXXXXXXX` |

### Step 4: Activate

The workflow runs automatically on the cron schedule. To test immediately:

1. Go to https://github.com/avraaws2022/nidriving/actions
2. Click **"DVA Slot Checker"** on the left
3. Click **"Run workflow"** > **"Run workflow"**
4. Check your WhatsApp for the confirmation message

---

## Schedule

| Setting | Value |
|---------|-------|
| **Frequency** | Every 25 minutes |
| **Days** | Monday to Saturday |
| **Hours** | 7:00 AM - 5:00 PM (UK time) |
| **Cron (UTC)** | `0,25,50 6-16 * * 1-6` |

DVA releases Category B appointments **3 months ahead** on the **first working day of each month**. Cancellations appear randomly.

---

## Notifications

### When slots ARE found:
```
🚗 DVA DRIVING TEST SLOT FOUND!

Centres: HYDEBANK, BALMORAL
  - HYDEBANK: Available

⚡ Book NOW before it's taken!
🔗 https://dva-bookings.nidirect.gov.uk/BookDriver/Driver/DriverSearch

Checked: 09:25:00
```

### When NO slots available:
```
DVA Check: NO SLOTS
Centres: HYDEBANK, BALMORAL
Checked: 2026-07-07 09:25
Next check in 25 min.
```

---

## File Structure

```
nidriving/
├── .github/
│   └── workflows/
│       └── check_slots.yml   ← GitHub Actions cron job
├── checker.py                ← Core: DVA scraping + WhatsApp alerts
├── scheduler.py              ← Local runner (alternative to GitHub Actions)
├── config.json               ← Local config (git-ignored, not needed for GH Actions)
├── .gitignore
└── README.md                 ← This file
```

---

## Running Locally (Optional)

If you prefer running on your own machine instead of GitHub Actions:

```bash
# Install dependencies
pip install requests beautifulsoup4

# Edit config.json with your details
# Then run:
python3 scheduler.py
```

For background execution:
```bash
nohup python3 scheduler.py > logs/scheduler.log 2>&1 &
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| GitHub Action fails with `KeyError` | Check all 6 secrets are added correctly |
| No WhatsApp received | Ensure you joined Twilio sandbox (send the join code) |
| "Access forbidden" from DVA | Site may be down or licence number incorrect |
| SSL errors (local only) | Corporate proxy issue; add `verify=False` to requests |
| Missed checks | GitHub Actions cron can delay up to 15 min under load |

---

## Important Notes

- This tool **monitors only**. You must **book the slot manually** when alerted.
- DVA website is only accessible during certain hours.
- Don't reduce check interval below 15 minutes (respect their servers).
- Twilio free trial gives you enough credits for months of notifications.
- The Twilio WhatsApp sandbox requires re-joining every 72 hours of inactivity.

---

## Tech Stack

- **Python 3.12** — requests + BeautifulSoup
- **GitHub Actions** — free cron scheduling
- **Twilio** — WhatsApp message delivery
- **DVA nidirect** — NI driving test booking system
