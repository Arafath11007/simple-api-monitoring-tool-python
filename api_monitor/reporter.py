"""Reporter: generates clean, standalone daily HTML reports using Jinja2."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
from jinja2 import Template

from api_monitor.exceptions import StorageError
from api_monitor.storage import DailySummary

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>API Health Report - {{ summary.date_str }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 30px; background-color: #f7f9fa; color: #333; }
        .container { max-width: 1100px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.06); }
        h1, h2, h3 { color: #1a202c; }
        .header-meta { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #edf2f7; padding-bottom: 15px; margin-bottom: 25px; }
        .score-card { font-size: 24px; font-weight: bold; padding: 10px 18px; border-radius: 6px; }
        .score-good { background: #e6fffa; color: #234e52; }
        .score-warn { background: #fffaf0; color: #7b341e; }
        .score-bad { background: #fff5f5; color: #742a2a; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 30px; }
        th { background-color: #f8fafc; text-align: left; padding: 12px; border-bottom: 2px solid #e2e8f0; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; }
        td { padding: 12px; border-bottom: 1px solid #edf2f7; font-size: 14px; }
        .status-badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; color: white; }
        .status-PASS { background-color: #22c55e; }
        .status-SLOW { background-color: #f59e0b; }
        .status-FAIL { background-color: #ef4444; }
        .status-ERROR { background-color: #b91c1c; }
        .fail-box { background: #fef2f2; border: 1px solid #fee2e2; border-radius: 6px; padding: 15px; margin-bottom: 25px; }
        .latency-bar-container { display: flex; align-items: center; }
        .footer { margin-top: 35px; padding-top: 15px; border-top: 1px solid #edf2f7; font-size: 12px; color: #94a3b8; }
    </style>
</head>
<body>
<div class="container">
    <div class="header-meta">
        <div>
            <h1 style="margin: 0 0 6px 0;">API Health Daily Report</h1>
            <span style="color: #64748b; font-size: 14px;">Date: <strong>{{ summary.date_str }}</strong> &bull; Total Executed Checks: <strong>{{ summary.total_checks }}</strong></span>
        </div>
        <div class="score-card {% if summary.overall_health_pct >= 99 %}score-good{% elif summary.overall_health_pct >= 90 %}score-warn{% else %}score-bad{% endif %}">
            {{ summary.overall_health_pct }}% Health
        </div>
    </div>

    <h2>Endpoint Summary</h2>
    <table>
        <thead>
            <tr>
                <th>Endpoint</th>
                <th>Uptime %</th>
                <th>Checks</th>
                <th>Failures</th>
                <th>Avg Latency</th>
                <th>Max Latency</th>
                <th>Latency Visual</th>
                <th>Last Status</th>
            </tr>
        </thead>
        <tbody>
            {% for ep in summary.endpoint_metrics %}
            <tr>
                <td><strong>{{ ep.name }}</strong><br><small style="color: #64748b;">{{ ep.url }}</small></td>
                <td><strong>{{ ep.uptime_pct }}%</strong></td>
                <td>{{ ep.total_checks }}</td>
                <td>{{ ep.failure_count }}</td>
                <td>{{ ep.avg_latency_ms }} ms</td>
                <td>{{ ep.max_latency_ms }} ms</td>
                <td style="width: 140px;">
                    <div class="latency-bar-container">
                        {% set bar_width = [ep.avg_latency_ms / 20.0, 100.0] | min %}
                        <svg width="100" height="14" style="background:#e2e8f0; border-radius:3px;">
                            <rect width="{{ bar_width }}" height="14" fill="{% if ep.avg_latency_ms < 500 %}#22c55e{% elif ep.avg_latency_ms < 1500 %}#f59e0b{% else %}#ef4444{% endif %}" rx="3"/>
                        </svg>
                    </div>
                </td>
                <td><span class="status-badge status-{{ ep.last_status }}">{{ ep.last_status }}</span></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    {% if summary.failures %}
    <h2>Failures & Errors ({{ summary.failures | length }})</h2>
    <div class="fail-box">
        <table style="margin: 0; background: transparent;">
            <thead>
                <tr>
                    <th style="background: transparent;">Timestamp</th>
                    <th style="background: transparent;">Endpoint</th>
                    <th style="background: transparent;">Status</th>
                    <th style="background: transparent;">HTTP Code</th>
                    <th style="background: transparent;">Reason</th>
                </tr>
            </thead>
            <tbody>
                {% for f in summary.failures %}
                <tr>
                    <td>{{ f.timestamp }}</td>
                    <td><strong>{{ f.endpoint }}</strong></td>
                    <td><span class="status-badge status-{{ f.status }}">{{ f.status }}</span></td>
                    <td>{{ f.http_status }}</td>
                    <td style="color: #991b1b;">{{ f.reason }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    <div class="footer">
        Generated on {{ gen_time }} | Config file: {{ config_file }} | Self-contained offline report
    </div>
</div>
</body>
</html>
"""


def generate_daily_html_report(summary: DailySummary, output_dir: str = "./reports", config_file: str = "config/config.yaml") -> Path:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    target_file = out_path / f"{summary.date_str}.html"

    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        summary=summary,
        gen_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        config_file=config_file,
    )

    # Atomic write: write to temp file then rename
    try:
        with tempfile.NamedTemporaryFile("w", dir=str(out_path), delete=False, encoding="utf-8") as tf:
            tf.write(html_content)
            temp_name = tf.name
        Path(temp_name).replace(target_file)
    except Exception as e:
        raise StorageError(f"Failed to write HTML report {target_file}: {e}")

    return target_file
