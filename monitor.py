"""Main runner and CLI entry point for API Health Monitor."""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

from api_monitor.alert_state import AlertStateManager
from api_monitor.config_loader import load_config
from api_monitor.exceptions import ConfigError
from api_monitor.logger import setup_logger
from api_monitor.notifier.email_notifier import EmailNotifier
from api_monitor.notifier.slack_notifier import SlackNotifier
from api_monitor.reporter import generate_daily_html_report
from api_monitor.results import Status
from api_monitor.runner import run_checks
from api_monitor.storage import aggregate_daily_csv, append_to_daily_csv

# Load .env variables at startup
load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="API Health & Uptime Monitor")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML configuration file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--only",
        metavar="ENDPOINT_NAME",
        help="Run health check only for a specific endpoint name",
    )
    parser.add_argument(
        "--daily-summary",
        action="store_true",
        help="Send daily summary notification without running checks (or after checking)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 1. Load Configuration
    try:
        config = load_config(args.config)
    except ConfigError as ce:
        print(f"Configuration Error: {ce}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error loading config: {e}", file=sys.stderr)
        return 2

    # 2. Setup Logger
    logger = setup_logger(config.settings.log_file)
    logger.info("=== Starting API Health Check Run ===")

    # Optional Pre-flight Auth Hook: Obtain token dynamically from login API
    if config.auth_hook.enabled and config.auth_hook.login_url:
        logger.info(f"Authenticating via login hook: {config.auth_hook.login_url}")
        token = fetch_auth_token(config.auth_hook, logger)
        if token:
            # Populate environment variable so all subsequent endpoints receive the token
            import os
            os.environ[config.auth_hook.auth_env] = token
            # Inject Authorization header into endpoints expecting this auth_env
            for ep in config.endpoints:
                if ep.auth_env == config.auth_hook.auth_env:
                    ep.headers["Authorization"] = f"Bearer {token}"
            logger.info(f"✓ Bearer token acquired dynamically and injected for {config.auth_hook.auth_env}")
        else:
            logger.warning(f"Could not retrieve token from {config.auth_hook.login_url}; proceeding with existing environment")

    # Handle --only filter
    endpoints_to_run = config.endpoints
    if args.only:
        endpoints_to_run = [ep for ep in config.endpoints if ep.name.lower() == args.only.lower()]
        if not endpoints_to_run:
            logger.error(f"No endpoint found matching --only '{args.only}'")
            return 2

    # Handle --daily-summary standalone
    if args.daily_summary and not endpoints_to_run:
        return handle_daily_summary(config, logger, args.config)

    # 3. Execute Checks
    logger.info(f"Checking {len(endpoints_to_run)} endpoint(s) with {config.settings.max_workers} workers...")
    results = run_checks(endpoints_to_run, config.settings)

    has_failures = False
    for r in results:
        status_label = r.status.value
        log_msg = f"[{status_label}] {r.endpoint_name} ({r.url}) - Latency: {r.response_time_ms}ms"
        if r.error_message:
            log_msg += f" | Reason: {r.error_message}"

        if r.status in (Status.FAIL, Status.ERROR):
            has_failures = True
            logger.warning(log_msg)
        elif r.status == Status.SLOW:
            logger.info(log_msg + " (SLOW)")
        else:
            logger.info(log_msg)

    # 4. Storage & Reporting
    csv_path = append_to_daily_csv(results, output_dir=config.settings.output_dir)
    logger.info(f"✓ Daily CSV updated: {csv_path.resolve()}")

    summary = aggregate_daily_csv(csv_path)
    html_path = generate_daily_html_report(summary, output_dir=config.settings.output_dir, config_file=args.config)
    logger.info(f"✓ Daily HTML report generated: {html_path.resolve()}")

    # 5. Alert Notifications (with Cooldown)
    cooldown_manager = AlertStateManager()
    alerts_to_send = []

    for r in results:
        if r.status in (Status.FAIL, Status.ERROR):
            if cooldown_manager.should_alert(r.endpoint_name, config.settings.alert_cooldown_minutes):
                alerts_to_send.append(r)
                cooldown_manager.record_alert(r.endpoint_name)
            else:
                logger.info(f"Alert suppressed for '{r.endpoint_name}' (inside {config.settings.alert_cooldown_minutes}m cooldown)")

    if alerts_to_send:
        logger.info(f"Dispatching alerts for {len(alerts_to_send)} endpoint(s)...")
        # Slack
        if config.alerts.slack.enabled:
            SlackNotifier().send_failure_alert(alerts_to_send, str(html_path))
        # Email
        if config.alerts.email.enabled:
            EmailNotifier(config.alerts.email).send_failure_alert(alerts_to_send, str(html_path))

    # Optional daily summary if requested
    if args.daily_summary:
        handle_daily_summary(config, logger, args.config)

    logger.info("=== Run Complete ===")
    return 1 if has_failures else 0


def handle_daily_summary(config, logger, config_file: str) -> int:
    from datetime import date
    today_str = date.today().isoformat()
    csv_path = Path(config.settings.output_dir) / f"{today_str}.csv"
    if not csv_path.exists():
        logger.warning(f"No checks recorded today ({csv_path}), summary empty.")
        return 0

    summary = aggregate_daily_csv(csv_path)
    html_path = Path(config.settings.output_dir) / f"{today_str}.html"

    lines = [
        f"Daily Health Summary for {summary.date_str}",
        f"Overall Health: {summary.overall_health_pct}%",
        f"Total Checks: {summary.total_checks}",
        "",
        "Endpoints:",
    ]
    for ep in summary.endpoint_metrics:
        lines.append(f" - {ep.name}: {ep.uptime_pct}% uptime, {ep.failure_count} failures (Avg: {ep.avg_latency_ms}ms)")

    text = "\n".join(lines)
    if config.alerts.slack.enabled:
        SlackNotifier().send_daily_summary(text, str(html_path))
    if config.alerts.email.enabled:
        EmailNotifier(config.alerts.email).send_daily_summary(text, str(html_path))

    return 0


def fetch_auth_token(auth_hook, logger) -> str | None:
    import requests
    try:
        method = auth_hook.method.upper()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        resp = requests.request(
            method=method,
            url=auth_hook.login_url,
            json=auth_hook.payload,
            headers=headers,
            timeout=10
        )
        if resp.status_code >= 400:
            logger.warning(f"Login hook returned HTTP {resp.status_code}: {resp.text}")
            return None

        data = resp.json()
        # Navigate dot-delimited json path (e.g. "token" or "data.token")
        keys = auth_hook.token_json_path.split(".")
        val = data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return None

        if isinstance(val, str) and val:
            return val
        return None
    except Exception as e:
        logger.error(f"Failed to fetch auth token via login hook: {e}")
        return None


if __name__ == "__main__":
    sys.exit(main())
