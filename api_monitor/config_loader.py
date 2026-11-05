"""Configuration loader and schema validator."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from api_monitor.exceptions import ConfigError

VALID_METHODS = {"GET", "POST", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"}
VALID_JSON_TYPES = {"str", "int", "float", "bool", "list", "dict"}


@dataclass
class Settings:
    default_timeout_seconds: int = 10
    slow_threshold_ms: float = 1500.0
    retries: int = 2
    retry_backoff_seconds: float = 2.0
    max_workers: int = 10
    output_dir: str = "./reports"
    log_file: str = "./logs/monitor.log"
    alert_cooldown_minutes: int = 60


@dataclass
class Endpoint:
    name: str
    url: str
    method: str = "GET"
    expected_status: int = 200
    timeout_seconds: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    json: Any = None
    auth_env: str | None = None
    expected_json: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class EmailAlertConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    from_addr: str = ""
    to_addrs: list[str] = field(default_factory=list)


@dataclass
class SlackAlertConfig:
    enabled: bool = False


@dataclass
class AlertsConfig:
    email: EmailAlertConfig = field(default_factory=EmailAlertConfig)
    slack: SlackAlertConfig = field(default_factory=SlackAlertConfig)


@dataclass
class MonitorConfig:
    settings: Settings
    endpoints: list[Endpoint]
    alerts: AlertsConfig


def resolve_env_vars(data: Any) -> Any:
    """Recursively resolves ${VAR_NAME}, ${VAR:-default}, or $VAR from os.environ."""
    if isinstance(data, str):
        def repl(match: re.Match) -> str:
            if match.group(1):  # ${VAR:-default}
                var_name = match.group(1)
                default_val = match.group(2) if match.group(2) is not None else ""
                return os.environ.get(var_name, default_val)
            if match.group(3):  # ${VAR}
                return os.environ.get(match.group(3), "")
            if match.group(4):  # $VAR
                return os.environ.get(match.group(4), match.group(0))
            return match.group(0)

        pattern = r"\$\{([A-Za-z0-9_]+):-([^}]*)\}|\$\{([A-Za-z0-9_]+)\}|\$([A-Za-z0-9_]+)"
        return re.sub(pattern, repl, data)
    elif isinstance(data, dict):
        return {k: resolve_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [resolve_env_vars(elem) for elem in data]
    return data


def load_config(config_path: str | Path) -> MonitorConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except Exception as e:
        raise ConfigError(f"Failed to parse YAML configuration: {e}")

    if not isinstance(raw_data, dict):
        raise ConfigError("Invalid configuration format: top level must be a YAML mapping")

    raw_data = resolve_env_vars(raw_data)

    # 1. Parse Settings
    raw_settings = raw_data.get("settings", {})
    settings = Settings(
        default_timeout_seconds=int(raw_settings.get("default_timeout_seconds", 10)),
        slow_threshold_ms=float(raw_settings.get("slow_threshold_ms", 1500.0)),
        retries=int(raw_settings.get("retries", 2)),
        retry_backoff_seconds=float(raw_settings.get("retry_backoff_seconds", 2.0)),
        max_workers=int(raw_settings.get("max_workers", 10)),
        output_dir=raw_settings.get("output_dir", "./reports"),
        log_file=raw_settings.get("log_file", "./logs/monitor.log"),
        alert_cooldown_minutes=int(raw_settings.get("alert_cooldown_minutes", 60)),
    )

    # 2. Parse Endpoints
    raw_endpoints = raw_data.get("endpoints", [])
    if not isinstance(raw_endpoints, list):
        raise ConfigError("'endpoints' section must be a list")

    endpoints = []
    seen_names = set()

    for item in raw_endpoints:
        if not isinstance(item, dict):
            raise ConfigError(f"Endpoint item must be a mapping: {item}")

        name = item.get("name")
        if not name or not isinstance(name, str):
            raise ConfigError(f"Endpoint missing a valid 'name': {item}")
        if name in seen_names:
            raise ConfigError(f"Duplicate endpoint name found: '{name}'")
        seen_names.add(name)

        url = item.get("url")
        if not url or not isinstance(url, str):
            raise ConfigError(f"Endpoint '{name}' is missing a 'url'")
        
        parsed_url = urlparse(url)
        if parsed_url.scheme.lower() not in ("http", "https") or not parsed_url.netloc:
            raise ConfigError(f"Endpoint '{name}' has invalid URL scheme or host: '{url}'")

        method = str(item.get("method", "GET")).upper()
        if method not in VALID_METHODS:
            raise ConfigError(f"Endpoint '{name}' has unsupported HTTP method: '{method}'")

        expected_json = item.get("expected_json", {})
        if expected_json and isinstance(expected_json, dict):
            for key, expected_type in expected_json.items():
                if expected_type not in VALID_JSON_TYPES:
                    raise ConfigError(
                        f"Endpoint '{name}' specified invalid expected_json type '{expected_type}' for key '{key}'. "
                        f"Must be one of: {sorted(VALID_JSON_TYPES)}"
                    )

        # Resolve auth_env if present
        headers = dict(item.get("headers", {}))
        auth_env_var = item.get("auth_env")
        if auth_env_var:
            token = os.environ.get(auth_env_var)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        ep = Endpoint(
            name=name,
            url=url,
            method=method,
            expected_status=int(item.get("expected_status", 200)),
            timeout_seconds=item.get("timeout_seconds"),
            headers=headers,
            body=item.get("data") or item.get("body"),
            json=item.get("json"),
            auth_env=auth_env_var,
            expected_json=expected_json if isinstance(expected_json, dict) else {},
            enabled=bool(item.get("enabled", True)),
        )
        endpoints.append(ep)

    # 3. Parse Alerts
    raw_alerts = raw_data.get("alerts", {})
    email_raw = raw_alerts.get("email", {})
    slack_raw = raw_alerts.get("slack", {})

    alerts = AlertsConfig(
        email=EmailAlertConfig(
            enabled=bool(email_raw.get("enabled", False)),
            smtp_host=email_raw.get("smtp_host", ""),
            smtp_port=int(email_raw.get("smtp_port", 587)),
            from_addr=email_raw.get("from_addr", ""),
            to_addrs=email_raw.get("to_addrs", []),
        ),
        slack=SlackAlertConfig(
            enabled=bool(slack_raw.get("enabled", False))
        ),
    )

    return MonitorConfig(settings=settings, endpoints=endpoints, alerts=alerts)
