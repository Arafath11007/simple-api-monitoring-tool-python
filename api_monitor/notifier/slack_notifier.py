"""Slack notification sender via Incoming Webhook."""

import json
import logging
import os
import requests

from api_monitor.notifier.base import BaseNotifier, format_failure_message
from api_monitor.results import CheckResult

logger = logging.getLogger("api_monitor")


class SlackNotifier(BaseNotifier):
    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")

    def send_failure_alert(self, failed_results: list[CheckResult], report_path: str) -> None:
        if not self.webhook_url:
            logger.warning("Slack notification skipped: SLACK_WEBHOOK_URL not configured")
            return

        text = format_failure_message(failed_results, report_path)
        payload = {"text": text}

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=5)
            if resp.status_code >= 400:
                logger.error(f"Slack webhook failed with HTTP {resp.status_code}: {resp.text}")
            else:
                logger.info("✓ Slack failure alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to post alert to Slack webhook: {e}")

    def send_daily_summary(self, summary_text: str, report_path: str) -> None:
        if not self.webhook_url:
            return

        payload = {"text": f"📊 *API Health Daily Summary*\n\n{summary_text}\n\nReport: `{report_path}`"}
        try:
            requests.post(self.webhook_url, json=payload, timeout=5)
            logger.info("✓ Slack daily summary sent successfully")
        except Exception as e:
            logger.error(f"Failed to send daily summary to Slack: {e}")
