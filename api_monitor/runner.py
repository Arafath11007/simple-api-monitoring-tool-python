"""Concurrent runner for endpoint checks."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from api_monitor.config_loader import Endpoint, Settings
from api_monitor.results import CheckResult, Status


def create_session(pool_size: int = 10) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def run_checks(endpoints: list[Endpoint], settings: Settings) -> list[CheckResult]:
    """Runs all enabled endpoints concurrently using ThreadPoolExecutor."""
    enabled_endpoints = [ep for ep in endpoints if ep.enabled]
    if not enabled_endpoints:
        return []

    worker_count = min(settings.max_workers, max(len(enabled_endpoints), 1))
    results: list[CheckResult | None] = [None] * len(enabled_endpoints)

    with create_session(pool_size=worker_count) as session:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_index = {
                executor.submit(check_endpoint_safe, ep, settings, session): idx
                for idx, ep in enumerate(enabled_endpoints)
            }

            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                results[idx] = future.result()

    return [r for r in results if r is not None]


def check_endpoint_safe(endpoint: Endpoint, settings: Settings, session: requests.Session) -> CheckResult:
    from api_monitor.checker import check_endpoint
    try:
        return check_endpoint(endpoint, settings, session)
    except Exception as e:
        from datetime import datetime, timezone
        return CheckResult(
            endpoint_name=endpoint.name,
            url=endpoint.url,
            timestamp=datetime.now(timezone.utc),
            status=Status.ERROR,
            http_status=None,
            response_time_ms=None,
            error_message=f"Unhandled runner exception: {e}",
            attempts=1,
        )
