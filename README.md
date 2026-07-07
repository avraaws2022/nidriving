# NI DVA Driving Test Slot Checker

Monitors the NI DVA booking system for available driving test slots at **Hydepark** and **Balmoral** test centres. Sends email alerts when a slot is found.

## How It Works

```
┌────────────────────────────────────────────────────┐
│  Scheduler runs Mon-Sat, 7:00 AM - 5:00 PM        │
│  Every 25 minutes:                                 │
│                                                    │
│  1. Opens DVA booking page                         │
│  2. Submits your licence details                   │
│  3. Checks for available slots at your centres     │
│  4. If found → Email alert + Desktop notification  │
│  5. You open the link and book manually            │
└────────────────────────────────────────────────────┘
```

## Setup

### 1. Install Python dependencies

```bash
pip install requests beautifulsoup4
```

### 2. Configure your details

Edit `config.json`:

```json
{
    "dva_booking": {
        "licence_number": "YOUR_8_DIGIT_LICENCE_NUMBER",
        "theory_cert_number": "YOUR_THEORY_CERT_NUMBER",
        "date_of_birth": "DD/MM/YYYY",
        "preferred_centres": ["HYDEPARK", "BALMORAL"]
    }
}
```

### 3. Set up email alerts

For Gmail, you need an **App Password** (not your regular password):
1. Go to https://myaccount.google.com/apppasswords
2. Generate a new app password for "Mail"
3. Put it in `config.json` under `email.sender_password`

```json
{
    "email": {
        "enabled": true,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_email": "your@gmail.com",
        "sender_password": "xxxx xxxx xxxx xxxx",
        "recipient_email": "your@gmail.com"
    }
}
```

### 4. Run the checker

**Single check (test):**
```bash
python3 checker.py
```

**Continuous monitoring:**
```bash
python3 scheduler.py
```

**Run in background (keeps running after closing terminal):**
```bash
nohup python3 scheduler.py &
```

## Schedule

Default schedule (configurable in `config.json`):
- **Days:** Monday to Saturday
- **Hours:** 7:00 AM - 5:00 PM
- **Interval:** Every 25 minutes

## Files

```
nidriving/
├── config.json     ← Your details (EDIT THIS)
├── checker.py      ← Slot checking logic + email alerts
├── scheduler.py    ← Runs checker on schedule
├── logs/           ← Check logs & last HTML response
├── .gitignore      ← Protects config.json
└── README.md       ← This file
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No token found" | DVA site may have changed structure. Check logs/last_response.html |
| Email not sending | Use Gmail App Password, not regular password |
| "Outside schedule" | Check your system clock matches the configured timezone |
| No slots ever found | Slots are released monthly on 1st working day. Be ready! |

## Tips

- DVA releases **Cat B** appointments **3 months ahead** on the **first working day of each month**
- Run the checker early on release day (from 7 AM)
- Cancellations appear randomly throughout the month
- The checker saves the last HTML response in `logs/` for debugging

## Important Notes

- This tool only **monitors** for slots. You must **book manually**.
- Be respectful of the DVA server - don't reduce the interval below 15 minutes.
- Your credentials stay local in `config.json` (git-ignored).
