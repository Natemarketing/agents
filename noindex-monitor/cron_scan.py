#!/usr/bin/env python3
"""
Daily cron job: sync sheet, scan all clients, post to Slack.

Add to crontab:
0 7 * * * cd /path/to/noindex-monitor && /path/to/venv/bin/python cron_scan.py
"""

import os
import sys

# Ensure the app directory is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from sheets import sync_clients_from_sheet
from scanner import run_full_scan
from slack_notify import send_slack_summary


def main():
    print("Syncing clients from Google Sheet...")
    count = sync_clients_from_sheet(app)
    print(f"Synced {count} clients.")

    print("Running full scan...")
    results = run_full_scan(app)
    for r in results:
        status = "FAIL" if r.get("fails", 0) > 0 else "PASS"
        print(f"  [{status}] {r.get('client', '?')} - {r.get('fails', 0)} fails / {r.get('total', 0)} URLs")

    print("Posting to Slack...")
    send_slack_summary(results)
    print("Done.")


if __name__ == "__main__":
    main()
