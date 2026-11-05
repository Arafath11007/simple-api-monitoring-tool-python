import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

def send_slack_notification(failed_results, webhook_url=None):
    """
    Sends an alert message to Slack via incoming webhook when APIs fail.
    """
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False, "SLACK_WEBHOOK_URL not configured"

    if not failed_results:
        return True, "No failed APIs to alert"

    count = len(failed_results)
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 API Alert: {count} Endpoint{'s' if count > 1 else ''} Failed!",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "The API monitoring script detected failures during its recent execution."
            }
        },
        {"type": "divider"}
    ]

    for item in failed_results:
        method = item.get("method", "GET")
        name = item.get("name", "Unknown API")
        url_text = item.get("url", "")
        code = item.get("status_code", "N/A")
        latency = item.get("latency_ms", 0)
        err = item.get("error_message", "Unknown error")

        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*API:*\n{name} (`{method}`) "},
                {"type": "mrkdwn", "text": f"*Status Code:*\n{code}"},
                {"type": "mrkdwn", "text": f"*Latency:*\n{latency} ms"},
                {"type": "mrkdwn", "text": f"*Error:*\n`{err}`"},
                {"type": "mrkdwn", "text": f"*URL:*\n{url_text}"}
            ]
        })
        blocks.append({"type": "divider"})

    payload = {
        "text": f"🚨 Alert: {count} API endpoint(s) failed health check!",
        "blocks": blocks
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("✓ Slack notification sent successfully.")
            return True, "Slack notification sent"
        else:
            msg = f"Slack webhook returned HTTP {resp.status_code}: {resp.text}"
            print(f"⚠️ {msg}")
            return False, msg
    except Exception as e:
        msg = f"Failed to send Slack alert: {str(e)}"
        print(f"⚠️ {msg}")
        return False, msg

def send_email_notification(failed_results):
    """
    Sends an email notification with failure details via SMTP.
    Requires SMTP environment variables:
      - SMTP_SERVER
      - SMTP_PORT (default: 587)
      - SMTP_USER
      - SMTP_PASSWORD
      - ALERT_TO_EMAIL
      - ALERT_FROM_EMAIL (defaults to SMTP_USER)
    """
    server = os.environ.get("SMTP_SERVER")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to_email = os.environ.get("ALERT_TO_EMAIL")
    from_email = os.environ.get("ALERT_FROM_EMAIL", user)

    if not (server and user and password and to_email):
        return False, "SMTP configuration missing (SMTP_SERVER, SMTP_USER, SMTP_PASSWORD, ALERT_TO_EMAIL)"

    if not failed_results:
        return True, "No failed APIs to alert"

    count = len(failed_results)
    subject = f"🚨 API Alert: {count} Endpoint{'s' if count > 1 else ''} Failed"

    # HTML Email body
    rows = "".join(
        f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd;">{r.get('name')}</td>
            <td style="padding: 8px; border: 1px solid #ddd; font-family: monospace;">{r.get('method', 'GET')}</td>
            <td style="padding: 8px; border: 1px solid #ddd; color: #d9534f; font-weight: bold;">{r.get('status_code')}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{r.get('latency_ms')} ms</td>
            <td style="padding: 8px; border: 1px solid #ddd; color: #b71c1c;">{r.get('error_message')}</td>
            <td style="padding: 8px; border: 1px solid #ddd; font-size: 12px;">{r.get('url')}</td>
        </tr>
        """
        for r in failed_results
    )

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; margin: 20px;">
        <h2 style="color: #d9534f;">API Health Alert: {count} Check(s) Failed</h2>
        <p>The automated API health checker encountered errors during its run:</p>
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="background: #f2f2f2; text-align: left;">
                <th style="padding: 8px; border: 1px solid #ddd;">Name</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Method</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Status</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Latency</th>
                <th style="padding: 8px; border: 1px solid #ddd;">Error Details</th>
                <th style="padding: 8px; border: 1px solid #ddd;">URL</th>
            </tr>
            {rows}
        </table>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_email, [to_email], msg.as_string())
        print(f"✓ Alert email successfully sent to {to_email}.")
        return True, "Email sent successfully"
    except Exception as e:
        msg_err = f"Failed to send email alert: {str(e)}"
        print(f"⚠️ {msg_err}")
        return False, msg_err

def notify_failures(results):
    """
    Checks results for failures and dispatches notifications via Slack and/or Email
    if the respective environment variables are configured.
    """
    failed = [r for r in results if not r.get("passed", False)]
    if not failed:
        return

    print(f"\n⚠️ {len(failed)} API(s) failed. Dispatching notifications...")

    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    if slack_url:
        send_slack_notification(failed, slack_url)
    else:
        print("ℹ️ Slack notification skipped (SLACK_WEBHOOK_URL not set).")

    smtp_server = os.environ.get("SMTP_SERVER")
    if smtp_server:
        send_email_notification(failed)
    else:
        print("ℹ️ Email notification skipped (SMTP_SERVER not set).")
