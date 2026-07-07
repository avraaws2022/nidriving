"""
NI DVA Slot Checker Scheduler
Runs the checker every 25 minutes during configured hours.
Usage: python3 scheduler.py
"""

import time
import json
import os
import signal
import sys
from datetime import datetime

from checker import DVASlotChecker, load_config, is_within_schedule, logger


def signal_handler(sig, frame):
    logger.info("\nStopping scheduler...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_scheduler():
    logger.info("=" * 60)
    logger.info("  NI DVA DRIVING TEST SLOT CHECKER")
    logger.info("  Monitoring: HYDEPARK & BALMORAL")
    logger.info("=" * 60)

    config = load_config()
    schedule = config["schedule"]
    interval = schedule["check_interval_minutes"] * 60  # Convert to seconds

    logger.info(f"  Schedule: {', '.join(d.capitalize() for d in schedule['days'])}")
    logger.info(f"  Hours: {schedule['start_hour']}:00 - {schedule['end_hour']}:00")
    logger.info(f"  Interval: Every {schedule['check_interval_minutes']} minutes")
    logger.info(f"  Centres: {', '.join(config['dva_booking']['preferred_centres'])}")
    logger.info(f"  Email to: {config['email']['recipient_email']}")
    logger.info("=" * 60)
    logger.info("  Press Ctrl+C to stop\n")

    check_count = 0
    slots_found_count = 0

    while True:
        # Reload config each cycle (allows live updates)
        try:
            config = load_config()
        except Exception as e:
            logger.error(f"Config reload failed: {e}")

        if is_within_schedule(config):
            check_count += 1
            now = datetime.now().strftime("%H:%M:%S")
            logger.info(f"\n[Check #{check_count}] {now}")

            try:
                checker = DVASlotChecker(config)
                found = checker.run_check()

                if found:
                    slots_found_count += 1
                    logger.info(f"  SLOTS FOUND! (total alerts: {slots_found_count})")
                else:
                    logger.info(f"  No slots. Next check in {schedule['check_interval_minutes']} min.")

            except Exception as e:
                logger.error(f"  Check failed: {e}")

            # Wait for next interval
            logger.info(f"  Sleeping {schedule['check_interval_minutes']} minutes...")
            time.sleep(interval)

        else:
            # Outside schedule - sleep 5 minutes then re-check
            now = datetime.now()
            day = now.strftime("%A")
            logger.info(f"  Outside schedule ({day} {now.strftime('%H:%M')}). Sleeping 5 min...")
            time.sleep(300)


if __name__ == "__main__":
    run_scheduler()
