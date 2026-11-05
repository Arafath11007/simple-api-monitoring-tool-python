"""Data models and status enums for API health monitor."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    SLOW = "SLOW"   # passed, but response time above slow_threshold_ms
    FAIL = "FAIL"   # response received, but wrong status code or JSON schema
    ERROR = "ERROR" # no usable response: timeout, DNS failure, connection refused


@dataclass
class CheckResult:
    endpoint_name: str
    url: str
    timestamp: datetime
    status: Status
    http_status: int | None
    response_time_ms: float | None
    error_message: str | None
    attempts: int
