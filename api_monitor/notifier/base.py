"""Notifier base interface and shared alert message formatting."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from api_monitor.results import CheckResult


class BaseNotifier(ABC):
    @abstractmethod
    def send_failure_alert(self, failed_results: list[CheckResult], report_path: str) -> None:
        pass

    @abstractmethod
    def send_daily_summary(self, summary_text: str, report_path: str) -> None:
        pass


def format_failure_message(failed_results: list[CheckResult], report_path: str) -> str:
    lines = [f"🚨 [API ALERT] {len(failed_results)} API endpoint(s) FAILING"]
    time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"Time: {time_str}")
    lines.append("-" * 40)

    for r in failed_results:
        lines.append(f"Endpoint: {r.endpoint_name}")
        lines.append(f"Status: {r.status.value} (HTTP {r.http_status or 'N/A'})")
        lines.append(f"Latency: {r.response_time_ms if r.response_time_ms is not None else 'N/A'} ms")
        lines.append(f"Reason: {r.error_message or 'Unknown error'}")
        lines.append("")

    lines.append("-" * 40)
    lines.append(f"Daily Report: {report_path}")
    return "\n".join(lines)
