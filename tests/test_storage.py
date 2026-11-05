import csv
from datetime import date
from api_monitor.results import CheckResult, Status
from datetime import datetime, timezone
from api_monitor.storage import append_to_daily_csv, aggregate_daily_csv

def test_storage_append_and_aggregate(tmp_path):
    now = datetime.now(timezone.utc)
    res1 = CheckResult(
        endpoint_name="API 1",
        url="https://api1.com",
        timestamp=now,
        status=Status.PASS,
        http_status=200,
        response_time_ms=120.0,
        error_message=None,
        attempts=1
    )
    res2 = CheckResult(
        endpoint_name="API 2",
        url="https://api2.com",
        timestamp=now,
        status=Status.FAIL,
        http_status=500,
        response_time_ms=450.0,
        error_message="Expected 200, got 500",
        attempts=3
    )

    today = date(2026, 11, 5)
    csv_file = append_to_daily_csv([res1, res2], output_dir=str(tmp_path), target_date=today)
    assert csv_file.exists()

    summary = aggregate_daily_csv(csv_file)
    assert summary.total_checks == 2
    assert summary.overall_health_pct == 50.0
    assert len(summary.endpoint_metrics) == 2
    assert len(summary.failures) == 1
    assert summary.failures[0]["endpoint"] == "API 2"
