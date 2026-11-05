# API Health Monitor

A production-ready, modular Python 3.11+ service that monitors project APIs on a schedule, validates status codes, response times, and JSON shapes, writes daily HTML and CSV reports, and sends email or Slack alerts on failure with configurable cooldown.

---

## Architecture & Features

- **YAML Configuration**: Supports `config/config.yaml` with schema validation, endpoint timeouts, headers, expected JSON keys and types, and secret resolution from environment variables (`auth_env`).
- **Concurrent Checks**: Multi-threaded execution using `concurrent.futures.ThreadPoolExecutor` with worker isolation and transient retries.
- **Deep Response Validation**:
  - HTTP status code matching.
  - Latency tracking and `SLOW` classification when threshold is exceeded.
  - JSON payload validation for expected keys and exact types (`str`, `int`, `float`, `bool`, `list`, `dict`).
- **Status Classification**:
  - `PASS`: Endpoint responded with expected status and valid JSON within latency threshold.
  - `SLOW`: Endpoint passed, but response time exceeded `slow_threshold_ms`.
  - `FAIL`: Unexpected status code or schema failure.
  - `ERROR`: Network timeout, DNS failure, or connection refused.
- **Daily Partitioned Reports**:
  - `reports/YYYY-MM-DD.csv`: Append-only daily raw data records.
  - `reports/YYYY-MM-DD.html`: Standalone, self-contained HTML report generated via Jinja2 with inline SVG latency bars, overall health score, and failure diagnostics.
- **Alerting & Cooldown Management**:
  - Slack incoming webhook notifications.
  - SMTP email alerts with STARTTLS.
  - `alert_state.json`: Suppresses repeated alerts for the same endpoint within `alert_cooldown_minutes`.
  - Daily summary digest (`--daily-summary`).
- **Exit Codes for CI / Cron**:
  - `0`: All checks passed.
  - `1`: One or more checks failed or errored.
  - `2`: Configuration or CLI error.

---

## Directory Structure

```text
api_monitoring_script/
├── api_monitor/             # Core monitoring package
│   ├── alert_state.py       # Cooldown tracking
│   ├── checker.py           # HTTP checker with latency & retries
│   ├── config_loader.py     # YAML loader & schema validator
│   ├── exceptions.py        # Custom exceptions hierarchy
│   ├── logger.py            # Rotating file & console logger
│   ├── monitor.py           # CLI entry point
│   ├── reporter.py          # Standalone Jinja2 HTML reporter
│   ├── results.py           # CheckResult dataclass & Status enum
│   ├── runner.py            # Concurrent ThreadPool runner
│   ├── storage.py           # Daily CSV storage & aggregation
│   ├── validator.py         # JSON key and type validator
│   └── notifier/            # Alert channels
│       ├── base.py          # Base notifier interface
│       ├── email_notifier.py # SMTP email sender
│       └── slack_notifier.py # Slack incoming webhook sender
├── config/
│   ├── config.example.yaml  # Example template (no secrets)
│   └── config.yaml          # Active configuration
├── docs/samples/            # Sample generated CSV and HTML reports
├── logs/                    # Rotating log files
├── reports/                 # Daily generated CSV and HTML reports
├── tests/                   # Pytest test suite
├── monitor.py               # Root CLI runner wrapper
├── pytest.ini               # Pytest configuration
├── requirements.txt         # Project dependencies
└── README.md                # Documentation
```

---

## Quickstart Guide

### 1. Installation

```bash
# Clone the repository and enter directory
cd api_monitoring_script

# Create virtual environment and activate
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy the example configuration to `config/config.yaml`:
```bash
cp config/config.example.yaml config/config.yaml
```

Set any necessary secrets in your environment or `.env`:
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export SMTP_USER="your-user"
export SMTP_PASSWORD="your-password"
export AUTH_BEARER_TOKEN="your-api-token"
```

### 3. Execution

```bash
# Run one full monitoring cycle
python monitor.py --config config/config.yaml

# Run check for only a specific endpoint
python monitor.py --config config/config.yaml --only "Users Health API"

# Send daily summary notification
python monitor.py --config config/config.yaml --daily-summary
```

---

## Running Automated Tests

Run the complete test suite with `pytest`:
```bash
./venv/bin/pytest
```

---

## Production Scheduling

### Linux / macOS (Cron)
```cron
# Run checks every 5 minutes
*/5 * * * * cd /opt/api_monitoring_script && ./venv/bin/python monitor.py --config config/config.yaml >> /var/log/api_monitor_cron.log 2>&1

# Send daily summary report every day at 18:00
0 18 * * * cd /opt/api_monitoring_script && ./venv/bin/python monitor.py --config config/config.yaml --daily-summary >> /var/log/api_monitor_cron.log 2>&1
```

### Windows Task Scheduler
Create a task running every 5 minutes:
- **Program/script**: `C:\api_monitoring_script\venv\Scripts\python.exe`
- **Arguments**: `monitor.py --config config\config.yaml`
- **Start in**: `C:\api_monitoring_script`
