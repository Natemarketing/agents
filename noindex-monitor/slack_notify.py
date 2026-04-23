"""
Slack notifications. Two-section format:
1. NEW noindexes (loud alert - the actual signal)
2. Summary of ongoing state (quiet context)
"""

import os
import requests

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
APP_URL = os.getenv("APP_URL", "")


def send_slack_summary(results: list):
    """Post a formatted scan summary to Slack."""
    if not SLACK_WEBHOOK_URL:
        return

    total_clients = len(results)
    total_urls = sum(r.get("total", 0) for r in results)
    total_fails = sum(r.get("fails", 0) for r in results)
    total_new = sum(r.get("new_fails", 0) for r in results)
    clients_with_new = [r for r in results if r.get("new_fails", 0) > 0]
    clients_with_ongoing = [
        r for r in results
        if r.get("fails", 0) > 0 and r.get("new_fails", 0) == 0
    ]

    blocks = []

    # Header
    if total_new > 0:
        header_text = f":rotating_light: {total_new} new noindexed URL(s) detected"
    elif total_fails > 0:
        header_text = f":eyes: {total_fails} ongoing noindex(es), no new issues"
    else:
        header_text = ":white_check_mark: All clear"

    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": header_text}
    })

    # Summary line
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*{total_clients}* clients scanned | "
                f"*{total_urls}* URLs checked | "
                f"*{total_fails}* total noindexes "
                f"({total_new} new)"
            )
        }
    })

    # NEW noindexes (loud section)
    if clients_with_new:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:rotating_light: New noindexes detected*"}
        })
        for r in clients_with_new:
            url_list = "\n".join(f"  • `{u}`" for u in r.get("new_urls", [])[:10])
            extra = ""
            if len(r.get("new_urls", [])) > 10:
                extra = f"\n  • _(+{len(r['new_urls']) - 10} more in dashboard)_"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{r['client']}* - {r['new_fails']} new\n{url_list}{extra}"
                }
            })

    # Ongoing noindexes (quieter)
    if clients_with_ongoing:
        blocks.append({"type": "divider"})
        ongoing_text = "*Ongoing (already flagged):*\n" + "\n".join(
            f"  • {r['client']} - {r['fails']} noindex(es)"
            for r in clients_with_ongoing
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": ongoing_text}
        })

    # Dashboard link
    if APP_URL:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"<{APP_URL}|Open dashboard>"
            }]
        })

    try:
        requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks}, timeout=10)
    except Exception:
        pass
