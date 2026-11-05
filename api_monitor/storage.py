"""Storage module: daily CSV append and statistical aggregation."""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from api_monitor.exceptions import StorageError
from api_monitor.results import CheckResult, Status

CSV_HEADERS = [
    "timestamp",
    "endpoint_name",
    "url",
    "status",
    "http_status",
    "response_time_ms",
    "attempts",
    "error_message",
]


@dataclass
class EndpointMetrics:
    name: str
    url: str
    total_checks: int
    passed_checks: int  # PASS and SLOW count as up
    uptime_pct: float
    avg_latency_ms: float
    max_latency_ms: float
    failure_count: int  # FAIL and ERROR
    last_status: str


@dataclass
class DailySummary:
    date_str: str
    total_checks: int
    overall_health_pct: float
    endpoint_metrics: list[EndpointMetrics]
    failures: list[dict[str, Any]]


def append_to_daily_csv(results: list[CheckResult], output_dir: str = "./reports", target_date: date | None = None) -> Path:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    today = target_date or date.today()
    csv_file = out_path / f"{today.isoformat()}.csv"

    file_exists = csv_file.exists()

    try:
        with open(csv_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(CSV_HEADERS)

            for r in results:
                writer.writerow([
                    r.timestamp.isoformat(),
                    r.endpoint_name,
                    r.url,
                    r.status.value,
                    r.http_status if r.http_status is not None else "",
                    r.response_time_ms if r.response_time_ms is not None else "",
                    r.attempts,
                    r.error_message or "",
                ])
    except Exception as e:
        raise StorageError(f"Failed to append results to daily CSV {csv_file}: {e}")

    return csv_file


def aggregate_daily_csv(csv_path: Path) -> DailySummary:
    if not csv_path.exists():
        raise StorageError(f"CSV file does not exist for aggregation: {csv_path}")

    rows: list[dict[str, str]] = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
    except Exception as e:
        raise StorageError(f"Failed to read CSV for aggregation: {e}")

    date_str = csv_path.stem

    if not rows:
        return DailySummary(
            date_str=date_str,
            total_checks=0,
            overall_health_pct=100.0,
            endpoint_metrics=[],
            failures=[],
        )

    # Group by endpoint
    by_endpoint: dict[str, list[dict[str, str]]] = {}
    failures: list[dict[str, Any]] = []

    for r in rows:
        name = r["endpoint_name"]
        by_endpoint.setdefault(name, []).append(r)
        status = r["status"]
        if status in (Status.FAIL.value, Status.ERROR.value):
            failures.append({
                "timestamp": r["timestamp"],
                "endpoint": name,
                "url": r["url"],
                "status": status,
                "http_status": r["http_status"] or "N/A",
                "reason": r["error_message"] or "Unknown",
            })

    endpoint_metrics: list[EndpointMetrics] = []
    total_all_checks = len(rows)
    total_all_up = 0

    for name, ep_rows in by_endpoint.items():
        url = ep_rows[0]["url"]
        count = len(ep_rows)
        # PASS and SLOW both count as UP
        up_count = sum(1 for x in ep_rows if x["status"] in (Status.PASS.value, Status.SLOW.value))
        fail_count = count - up_count
        total_all_up += up_count

        latencies = [
            float(x["response_time_ms"])
            for x in ep_rows
            if x["response_time_ms"] != "" and float(x["response_time_ms"]) >= 0
        ]
        avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
        max_lat = round(max(latencies), 1) if latencies else 0.0

        last_status = ep_rows[-1]["status"]
        uptime_pct = round((up_count / count) * 100, 1)

        endpoint_metrics.append(EndpointMetrics(
            name=name,
            url=url,
            total_checks=count,
            passed_checks=up_count,
            uptime_pct=uptime_pct,
            avg_latency_ms=avg_lat,
            max_latency_ms=max_lat,
            failure_count=fail_count,
            last_status=last_status,
        ))

    overall_pct = round((total_all_up / total_all_checks) * 100, 1) if total_all_checks else 100.0

    return DailySummary(
        date_str=date_str,
        total_checks=total_all_checks,
        overall_health_pct=overall_pct,
        endpoint_metrics=endpoint_metrics,
        failures=failures,
    )
