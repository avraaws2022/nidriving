"""
NI DVA Driving Test Slot Checker
Monitors dva-bookings.nidirect.gov.uk for available slots at preferred test centres.
"""

import json
import time
import os
import logging
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/checker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


class DVASlotChecker:
    """Checks NI DVA booking site for available driving test slots."""

    BASE_URL = "https://dva-bookings.nidirect.gov.uk"
    SEARCH_URL = f"{BASE_URL}/BookDriver/Driver/DriverSearch"
    SLOTS_URL = f"{BASE_URL}/BookDriver/Slot/SlotSearch"

    def __init__(self, config):
        self.config = config
        self.dva = config["dva_booking"]
        self.email_config = config.get("email", {"enabled": False})
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

    def get_verification_token(self, html):
        """Extract __RequestVerificationToken from form."""
        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if token_input:
            return token_input.get("value", "")
        return ""

    def search_driver(self):
        """Step 1: Submit driver search form with licence details."""
        logger.info("Fetching driver search page...")

        try:
            # Get the form page first (for CSRF token & cookies)
            resp = self.session.get(self.SEARCH_URL, timeout=30)
            resp.raise_for_status()

            token = self.get_verification_token(resp.text)
            logger.info(f"Got verification token: {token[:20]}..." if token else "No token found")

            # Submit the search form
            form_data = {
                "__RequestVerificationToken": token,
                "LicenceNumber": self.dva["licence_number"],
                "TheoryCertNumber": self.dva.get("theory_cert_number", ""),
                "DateOfBirth": self.dva.get("date_of_birth", ""),
                "TestCategory": self.dva.get("test_category", "B"),
            }

            logger.info(f"Submitting driver search for licence: {self.dva['licence_number'][:3]}***")

            resp = self.session.post(
                self.SEARCH_URL,
                data=form_data,
                timeout=30,
                allow_redirects=True
            )
            resp.raise_for_status()

            # Check if we got through or got an error
            if "error" in resp.text.lower() and "validation" in resp.text.lower():
                soup = BeautifulSoup(resp.text, "html.parser")
                errors = soup.find_all(class_="validation-summary-errors")
                if errors:
                    error_text = errors[0].get_text(strip=True)
                    logger.error(f"Validation error: {error_text}")
                    return None

            return resp

        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def check_available_slots(self):
        """Step 2: Check for available slots at preferred centres."""
        logger.info("=" * 50)
        logger.info("CHECKING FOR AVAILABLE SLOTS")
        logger.info(f"Centres: {', '.join(self.dva['preferred_centres'])}")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 50)

        # First authenticate/search
        search_resp = self.search_driver()
        if search_resp is None:
            logger.warning("Driver search failed. Will retry next cycle.")
            return []

        # Look for available slots in the response
        available_slots = []

        try:
            soup = BeautifulSoup(search_resp.text, "html.parser")

            # Try to find slot/centre information on the page
            # The DVA site typically shows available centres after driver search
            # Look for common patterns in booking systems

            # Pattern 1: Look for centre names and dates in tables
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    row_text = row.get_text().upper()
                    for centre in self.dva["preferred_centres"]:
                        if centre.upper() in row_text:
                            cells = row.find_all(["td", "th"])
                            slot_info = " | ".join(c.get_text(strip=True) for c in cells)
                            available_slots.append({
                                "centre": centre,
                                "details": slot_info,
                                "raw": row_text.strip()
                            })

            # Pattern 2: Look for links/buttons with centre names
            links = soup.find_all("a")
            for link in links:
                link_text = link.get_text().upper()
                for centre in self.dva["preferred_centres"]:
                    if centre.upper() in link_text:
                        href = link.get("href", "")
                        available_slots.append({
                            "centre": centre,
                            "details": link.get_text(strip=True),
                            "url": f"{self.BASE_URL}{href}" if href.startswith("/") else href
                        })

            # Pattern 3: Look for divs/spans with centre info
            for element in soup.find_all(["div", "span", "li", "option"]):
                text = element.get_text().upper()
                for centre in self.dva["preferred_centres"]:
                    if centre.upper() in text and "available" in text.lower():
                        available_slots.append({
                            "centre": centre,
                            "details": element.get_text(strip=True),
                        })

            # Pattern 4: Look for select options (dropdown of centres)
            selects = soup.find_all("select")
            for select in selects:
                options = select.find_all("option")
                for option in options:
                    opt_text = option.get_text().upper()
                    for centre in self.dva["preferred_centres"]:
                        if centre.upper() in opt_text:
                            available_slots.append({
                                "centre": centre,
                                "details": option.get_text(strip=True),
                                "value": option.get("value", "")
                            })

            # Pattern 5: Check for appointment/slot specific pages
            # Try navigating to slot search if we got redirected
            if "/Slot" in search_resp.url or "/slot" in search_resp.url:
                logger.info("Redirected to slot page - checking dates...")
                self._check_slot_page(soup, available_slots)

            # Try to follow to slot selection page
            if not available_slots:
                slot_links = soup.find_all("a", href=True)
                for sl in slot_links:
                    if "slot" in sl.get("href", "").lower() or "book" in sl.get("href", "").lower():
                        try:
                            slot_resp = self.session.get(
                                f"{self.BASE_URL}{sl['href']}" if sl['href'].startswith("/") else sl['href'],
                                timeout=30
                            )
                            slot_soup = BeautifulSoup(slot_resp.text, "html.parser")
                            self._check_slot_page(slot_soup, available_slots)
                        except Exception as e:
                            logger.debug(f"Could not follow slot link: {e}")
                        break

            # Also save raw HTML for debugging (last response only)
            debug_path = os.path.join("logs", "last_response.html")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(search_resp.text)
            logger.info(f"Saved response HTML to {debug_path}")

        except Exception as e:
            logger.error(f"Error parsing response: {e}")

        # Report findings
        if available_slots:
            # Deduplicate
            seen = set()
            unique_slots = []
            for slot in available_slots:
                key = f"{slot['centre']}_{slot.get('details', '')}"
                if key not in seen:
                    seen.add(key)
                    unique_slots.append(slot)

            logger.info(f"\n{'!' * 50}")
            logger.info(f"SLOTS FOUND: {len(unique_slots)} at preferred centres!")
            logger.info(f"{'!' * 50}")
            for slot in unique_slots:
                logger.info(f"  Centre: {slot['centre']}")
                logger.info(f"  Details: {slot.get('details', 'N/A')}")
                if "url" in slot:
                    logger.info(f"  Link: {slot['url']}")
                logger.info("")

            return unique_slots
        else:
            logger.info("No slots found at preferred centres this check.")
            return []

    def _check_slot_page(self, soup, available_slots):
        """Parse a slot/appointment selection page."""
        # Look for date/time elements
        for element in soup.find_all(["td", "a", "button", "div"]):
            text = element.get_text().upper()
            for centre in self.dva["preferred_centres"]:
                if centre.upper() in text:
                    # Found a reference to our preferred centre
                    parent = element.find_parent(["tr", "div", "section"])
                    if parent:
                        detail = parent.get_text(strip=True)[:200]
                    else:
                        detail = element.get_text(strip=True)
                    available_slots.append({
                        "centre": centre,
                        "details": detail,
                    })

    def send_email_alert(self, slots):
        """Send email notification about available slots."""
        if not self.email_config.get("enabled"):
            logger.info("Email alerts disabled in config.")
            return

        try:
            subject = f"DVA DRIVING TEST SLOT AVAILABLE - {', '.join(s['centre'] for s in slots)}"

            body = f"""
<html>
<body style="font-family: Arial, sans-serif; background: #f4f4f4; padding: 20px;">
<div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
    <h1 style="color: #2d7d46; margin-top: 0;">Driving Test Slot Found!</h1>
    <p style="color: #333; font-size: 16px;">Available slots detected at your preferred test centres:</p>

    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
        <tr style="background: #2d7d46; color: white;">
            <th style="padding: 12px; text-align: left;">Centre</th>
            <th style="padding: 12px; text-align: left;">Details</th>
        </tr>
"""
            for i, slot in enumerate(slots):
                bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
                body += f"""
        <tr style="background: {bg};">
            <td style="padding: 12px; font-weight: bold;">{slot['centre']}</td>
            <td style="padding: 12px;">{slot.get('details', 'Available')}</td>
        </tr>
"""

            body += f"""
    </table>

    <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <strong>Act fast!</strong> Book immediately before the slot is taken.
    </div>

    <a href="{self.dva['url']}" style="display: inline-block; background: #2d7d46; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
        Book Now on DVA
    </a>

    <p style="color: #666; font-size: 12px; margin-top: 30px;">
        Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
        StockPulseIND / NI Driving Test Checker
    </p>
</div>
</body>
</html>
"""

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email_config["sender_email"]
            msg["To"] = self.email_config["recipient_email"]
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(self.email_config["smtp_server"], self.email_config["smtp_port"]) as server:
                server.starttls()
                server.login(self.email_config["sender_email"], self.email_config["sender_password"])
                server.send_message(msg)

            logger.info(f"Email alert sent to {self.email_config['recipient_email']}")

        except Exception as e:
            logger.error(f"Failed to send email: {e}")

    def send_desktop_alert(self, slots):
        """Send macOS desktop notification."""
        if not self.config.get("notifications", {}).get("desktop_alert"):
            return

        centres = ", ".join(s["centre"] for s in slots)
        title = "DVA Test Slot Available!"
        message = f"Slots found at: {centres}. Book now!"

        try:
            subprocess.run([
                "osascript", "-e",
                f'display notification "{message}" with title "{title}" sound name "Glass"'
            ], check=False)
            logger.info("Desktop notification sent.")
        except Exception as e:
            logger.debug(f"Desktop notification failed: {e}")

    def send_sms_alert(self, slots):
        """Send SMS notification via Twilio."""
        sms_config = self.config.get("sms", {})
        if not sms_config.get("enabled"):
            logger.info("SMS alerts disabled in config.")
            return

        centres = ", ".join(s["centre"] for s in slots)
        message = (
            f"DVA TEST SLOT FOUND!\n"
            f"Centres: {centres}\n"
            f"Book NOW: {self.dva['url']}\n"
            f"Checked: {datetime.now().strftime('%H:%M')}"
        )

        try:
            account_sid = sms_config["account_sid"]
            auth_token = sms_config["auth_token"]
            from_number = sms_config["from_number"]
            to_number = sms_config["to_number"]

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            resp = requests.post(
                url,
                data={
                    "From": from_number,
                    "To": to_number,
                    "Body": message
                },
                auth=(account_sid, auth_token),
                timeout=30,
                verify=False
            )

            if resp.status_code in (200, 201):
                logger.info(f"SMS sent to {to_number}")
            else:
                logger.error(f"SMS failed: {resp.status_code} - {resp.text}")

        except Exception as e:
            logger.error(f"SMS alert failed: {e}")

    def send_whatsapp_alert(self, slots):
        """Send WhatsApp notification via Twilio."""
        wa_config = self.config.get("whatsapp", {})
        if not wa_config.get("enabled"):
            return

        centres = ", ".join(s["centre"] for s in slots)
        details = "\n".join(f"  - {s['centre']}: {s.get('details', 'Available')}" for s in slots)

        message = (
            f"🚗 DVA DRIVING TEST SLOT FOUND!\n\n"
            f"Centres: {centres}\n\n"
            f"{details}\n\n"
            f"⚡ Book NOW before it's taken!\n"
            f"🔗 {self.dva['url']}\n\n"
            f"Checked: {datetime.now().strftime('%H:%M:%S')}"
        )

        try:
            account_sid = wa_config["account_sid"]
            auth_token = wa_config["auth_token"]
            from_number = wa_config["from_number"]
            to_number = wa_config["to_number"]

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            resp = requests.post(
                url,
                data={
                    "From": from_number,
                    "To": to_number,
                    "Body": message
                },
                auth=(account_sid, auth_token),
                timeout=30,
                verify=False
            )

            if resp.status_code in (200, 201):
                logger.info(f"WhatsApp alert sent to {to_number}")
            else:
                logger.error(f"WhatsApp send failed: {resp.status_code} - {resp.text}")

        except Exception as e:
            logger.error(f"WhatsApp alert failed: {e}")

    def send_no_slots_message(self):
        """Send a 'no slots' WhatsApp message to confirm checker is running."""
        wa_config = self.config.get("whatsapp", {})
        if not wa_config.get("enabled"):
            return

        message = (
            f"DVA Check: NO SLOTS\n"
            f"Centres: {', '.join(self.dva['preferred_centres'])}\n"
            f"Checked: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Next check in 25 min."
        )

        try:
            account_sid = wa_config["account_sid"]
            auth_token = wa_config["auth_token"]
            from_number = wa_config["from_number"]
            to_number = wa_config["to_number"]

            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

            resp = requests.post(
                url,
                data={
                    "From": from_number,
                    "To": to_number,
                    "Body": message
                },
                auth=(account_sid, auth_token),
                timeout=30,
                verify=False
            )

            if resp.status_code in (200, 201):
                logger.info(f"No-slots message sent to {to_number}")
            else:
                logger.error(f"No-slots message failed: {resp.status_code} - {resp.text}")

        except Exception as e:
            logger.error(f"No-slots message failed: {e}")

    def run_check(self):
        """Run a single check cycle."""
        slots = self.check_available_slots()

        if slots:
            self.send_sms_alert(slots)
            self.send_whatsapp_alert(slots)
            self.send_email_alert(slots)
            self.send_desktop_alert(slots)
            return True
        else:
            self.send_no_slots_message()
            return False


def is_within_schedule(config):
    """Check if current time is within the configured schedule."""
    schedule = config["schedule"]
    now = datetime.now()

    day_name = now.strftime("%A").lower()
    if day_name not in schedule["days"]:
        return False

    hour = now.hour
    if hour < schedule["start_hour"] or hour >= schedule["end_hour"]:
        return False

    return True


def run():
    """Main entry point - run a single check."""
    config = load_config()
    checker = DVASlotChecker(config)
    found = checker.run_check()
    return found


if __name__ == "__main__":
    run()
