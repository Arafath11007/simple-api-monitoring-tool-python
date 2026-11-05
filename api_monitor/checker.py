"""HTTP checker: executes one endpoint check with latency measurement."""

import time
from datetime import datetime, timezone
import requests
from api_monitor.config_loader import Endpoint, Settings
from api_monitor.results import CheckResult, Status
from api_monitor.validator import validate_json_body


def check_endpoint(endpoint: Endpoint, settings: Settings, session: requests.Session | None = None) -> CheckResult:
    """
    Performs HTTP check against an endpoint with retries on 5xx or connection/timeout errors.
    Does not retry on 4xx responses.
    """
    client = session or requests
    timeout = endpoint.timeout_seconds or settings.default_timeout_seconds
    max_retries = max(0, settings.retries)
    backoff = settings.retry_backoff_seconds

    attempts = 0
    last_status = Status.ERROR
    last_http_status = None
    last_latency_ms = None
    last_error_message = None

    while attempts <= max_retries:
        attempts += 1
        start_time = time.perf_counter()

        try:
            response = client.request(
                method=endpoint.method,
                url=endpoint.url,
                headers=endpoint.headers if endpoint.headers else None,
                data=endpoint.body,
                json=endpoint.json,
                timeout=timeout,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            last_http_status = response.status_code
            last_latency_ms = elapsed_ms

            # Check 1: Status code comparison (single int or list of accepted statuses)
            is_status_matched = (
                response.status_code in endpoint.expected_status
                if isinstance(endpoint.expected_status, list)
                else response.status_code == endpoint.expected_status
            )
            if not is_status_matched:
                last_status = Status.FAIL
                last_error_message = f"Expected HTTP {endpoint.expected_status}, got {response.status_code}"
                # If 5xx, retry with backoff unless last attempt
                if response.status_code >= 500 and attempts <= max_retries:
                    time.sleep(backoff)
                    continue
                # If 4xx, do not retry
                break

            # Check 2: JSON Schema and type validation
            if endpoint.expected_json:
                is_valid, reason = validate_json_body(response.text, endpoint.expected_json)
                if not is_valid:
                    last_status = Status.FAIL
                    last_error_message = reason
                    # Bad JSON response shouldn't be retried
                    break

            # Check 3: Latency classification (PASS vs SLOW)
            if elapsed_ms > settings.slow_threshold_ms:
                last_status = Status.SLOW
                last_error_message = None
            else:
                last_status = Status.PASS
                last_error_message = None

            # All checks succeeded
            break

        except requests.exceptions.Timeout:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            last_latency_ms = elapsed_ms
            last_status = Status.ERROR
            last_error_message = f"Request timed out (>{timeout}s)"
            if attempts <= max_retries:
                time.sleep(backoff)
                continue
            break

        except requests.exceptions.ConnectionError:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            last_latency_ms = elapsed_ms
            last_status = Status.ERROR
            last_error_message = "Connection failed / DNS resolution error"
            if attempts <= max_retries:
                time.sleep(backoff)
                continue
            break

        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            last_latency_ms = elapsed_ms
            last_status = Status.ERROR
            last_error_message = str(e)
            if attempts <= max_retries:
                time.sleep(backoff)
                continue
            break

    return CheckResult(
        endpoint_name=endpoint.name,
        url=endpoint.url,
        timestamp=datetime.now(timezone.utc),
        status=last_status,
        http_status=last_http_status,
        response_time_ms=last_latency_ms,
        error_message=last_error_message,
        attempts=attempts,
    )
