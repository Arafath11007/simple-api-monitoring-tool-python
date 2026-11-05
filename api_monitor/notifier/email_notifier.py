"""Email alert notifier using smtplib with STARTTLS."""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from api_monitor.config_loader import EmailAlertConfig
from api_monitor.notifier.base import BaseNotifier, format_failure_message
from api_monitor.results import CheckResult

logger = logging.getLogger("api_monitor")


class EmailNotifier(BaseNotifier):
    def __init__(self, config: EmailAlertConfig):
        self.config = config
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")

    def send_failure_alert(self, failed_results: list[CheckResult], report_path: str) -> None:
        if not self.config.enabled:
            return

        if not self.config.smtp_host or not self.config.to_addrs:
            logger.warning("Email notification skipped: missing smtp_host or to_addrs")
            return

        subject = f"[API ALERT] {len(failed_results)} Endpoint(s) Failing"
        body_text = format_failure_message(failed_results, report_path)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.from_addr or self.user
        msg["To"] = ", ".join(self.config.to_addrs)
        msg.attach(MIMEText(body_text, "plain"))

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10) as server:
                server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(msg["From"], self.config.to_addrs, msg.as_string())
            logger.info("✓ Failure alert email sent successfully")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def send_daily_summary(self, summary_text: str, report_path: str) -> None:
        if not self.config.enabled or not self.config.smtp_host or not self.config.to_addrs:
            return

        subject = "[API Health] Daily Summary Report"
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.from_addr or self.user
        msg["To"] = ", ".join(self.config.to_addrs)
        msg.attach(MIMEText(f"{summary_text}\n\nReport link: {report_path}", "plain"))

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10) as server:
                server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(msg["From"], self.config.to_addrs, msg.as_string())
            logger.info("✓ Daily summary email sent successfully")
        except Exception as e:
            logger.error(f"Failed to send daily summary email: {e}")
