# API Health & Uptime Monitoring Script

A high-performance, concurrent Python-based API health and uptime monitoring tool. It reads target endpoint specifications from a JSON configuration file, executes automated health checks concurrently across multiple HTTP verbs, validates latency, status codes, response headers, and payloads, and outputs formatted CSV and HTML reports.

---

## Features

- **Concurrent Execution**: Uses Python's `ThreadPoolExecutor` to test multiple endpoints simultaneously without blocking.
- **Connection Pooling & Resiliency**: Built on `requests.Session` with `HTTPAdapter` and exponential backoff retry on transient 5xx errors.
- **Advanced HTTP Methods**: Supports `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, and `OPTIONS`.
- **Custom Payloads & Headers**: Send custom headers, query parameters, form data, or JSON payloads.
- **Authentication**: Built-in support for Bearer tokens and HTTP Basic Auth.
- **Secret Interpolation**: Supports `${ENV_VAR}` or `$ENV_VAR` syntax within endpoint configurations to keep secrets out of source control.
- **Proactive SSL Monitoring**: Pre-verifies SSL certificate expiration thresholds to catch expiring certificates early.
- **Detailed Reporting**: Generates both historical append-only CSV logs (`api_report.csv`) and a formatted HTML status dashboard (`api_report.html`).

---

## Project Structure

```text
api_monitoring_script/
├── apis.json           # Target endpoints & test definitions
├── main.py             # Monitoring engine, checker logic, and report generator
├── requirements.txt    # Project Python dependencies
├── api_report.csv      # Historical test run logs (appended each run)
├── api_report.html     # Color-coded HTML report summary
└── README.md           # Documentation & deployment guide
```

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.8 or higher
- `pip` and virtual environment support (`venv`)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd api_monitoring_script
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the monitor:**
   ```bash
   python main.py
   ```

---

## Endpoint Configuration (`apis.json`)

Configure your endpoints in [`apis.json`](apis.json). Here is a full example demonstrating the available schema options:

```json
[
  {
    "name": "User List (GET)",
    "url": "https://api.example.com/users",
    "method": "GET",
    "headers": {
      "Accept": "application/json"
    },
    "expected_status": 200,
    "max_latency_ms": 1500,
    "expected_keys": ["id", "name", "email"],
    "expected_headers": {
      "content-type": "application/json"
    },
    "check_ssl_cert": true,
    "min_ssl_days": 14
  },
  {
    "name": "Create Resource (POST)",
    "url": "https://api.example.com/items",
    "method": "POST",
    "auth": {
      "type": "bearer",
      "token": "${API_AUTH_TOKEN}"
    },
    "json": {
      "title": "Health Check Ping",
      "active": true
    },
    "expected_status": [200, 201],
    "max_latency_ms": 2000,
    "expected_keys": ["id", "title"]
  },
  {
    "name": "Basic Auth Endpoint",
    "url": "https://api.example.com/secure-data",
    "method": "GET",
    "auth": {
      "type": "basic",
      "username": "${BASIC_USER}",
      "password": "${BASIC_PASS}"
    },
    "expected_status": 200
  }
]
```

### Configuration Fields

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | *required* | Human-readable label for the API check |
| `url` | string | *required* | Target URL (supports `${ENV_VAR}` interpolation) |
| `method` | string | `"GET"` | HTTP verb (`GET`, `POST`, `PUT`, `DELETE`, etc.) |
| `headers` | object | `{}` | Custom HTTP headers |
| `params` | object | `null` | URL query string parameters |
| `json` | object | `null` | JSON payload to send in the request body |
| `data` | string/object | `null` | Form-encoded or raw body payload |
| `auth` | object | `null` | Authentication (`bearer` with `token`, or `basic` with `username`/`password`) |
| `expected_status` | int / list | `200` | Single HTTP code (e.g. `200`) or array of acceptable codes (e.g. `[200, 204]`) |
| `max_latency_ms` | int | `3000` | Latency threshold in milliseconds |
| `expected_keys` | list | `[]` | Keys that must exist in the response JSON |
| `expected_headers` | object | `{}` | Headers expected in the response (e.g. `{"content-type": "application/json"}`) |
| `timeout_s` | int | `10` | Request timeout in seconds |
| `verify_ssl` | bool | `true` | Verify SSL certificates during request |
| `check_ssl_cert` | bool | `false` | Explicitly verify remote SSL certificate expiration |
| `min_ssl_days` | int | `14` | Minimum days before SSL expiration before flagging failure |

---

## Deployment Options

### Option 1: Linux Systemd Timer (Recommended for Production VM)

To run the monitoring script automatically every 5 minutes on an Ubuntu/Debian/RHEL server:

1. **Deploy project to `/opt/api_monitoring_script`**:
   ```bash
   sudo mkdir -p /opt/api_monitoring_script
   sudo cp -r . /opt/api_monitoring_script
   cd /opt/api_monitoring_script
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

2. **Create the systemd service unit** (`/etc/systemd/system/api-monitor.service`):
   ```ini
   [Unit]
   Description=API Health Check Runner
   After=network.target

   [Service]
   Type=oneshot
   User=www-data
   WorkingDirectory=/opt/api_monitoring_script
   EnvironmentFile=-/opt/api_monitoring_script/.env
   ExecStart=/opt/api_monitoring_script/venv/bin/python main.py
   ```

3. **Create the systemd timer unit** (`/etc/systemd/system/api-monitor.timer`):
   ```ini
   [Unit]
   Description=Run API Health Check every 5 minutes

   [Timer]
   OnBootSec=1min
   OnUnitActiveSec=5min
   Unit=api-monitor.service

   [Install]
   WantedBy=timers.target
   ```

4. **Enable and start the timer:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now api-monitor.timer
   sudo systemctl status api-monitor.timer
   ```

---

### Option 2: Crontab

For lightweight scheduling, configure a cron job on your server:

```bash
crontab -e
```

Add the following line to execute every 5 minutes:
```cron
*/5 * * * * cd /opt/api_monitoring_script && ./venv/bin/python main.py >> /var/log/api_monitor.log 2>&1
```

---

### Option 3: Docker Deployment

You can package and run the monitor in a lightweight Docker container.

1. **Create a `Dockerfile`** (if containerizing):
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   CMD ["python", "main.py"]
   ```

2. **Build and run:**
   ```bash
   docker build -t api-monitor .
   docker run --rm -v $(pwd)/reports:/app api-monitor
   ```

---

### Option 4: CI/CD Pipeline (e.g., GitHub Actions)

Run health checks on a schedule or as a synthetic post-deployment verification test:

```yaml
name: API Monitoring Check

on:
  schedule:
    - cron: '*/15 * * * *'  # Runs every 15 minutes
  workflow_dispatch:

jobs:
  health-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run Monitoring Script
        env:
          API_AUTH_TOKEN: ${{ secrets.API_AUTH_TOKEN }}
        run: python main.py
      - name: Upload HTML & CSV Reports
        uses: actions/upload-artifact@v4
        with:
          name: api-reports
          path: |
            api_report.html
            api_report.csv
```

---

## Serving the HTML Dashboard

To view `api_report.html` in real-time on a server:

1. **Quick local preview:**
   ```bash
   python -m http.server 8080
   ```
   Open `http://localhost:8080/api_report.html` in your browser.

2. **Nginx Integration**:
   Symlink or copy `api_report.html` into your web root (e.g. `/var/www/html/api-status/`).
