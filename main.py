import csv
import json
import os
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry

# test configuration
CONFIG_DATA = []

# Ensure 'apis.json' exists locally
if not os.path.exists("apis.json"):
    with open("apis.json", "w", encoding="utf-8") as f:
        json.dump(CONFIG_DATA, f, indent=2)
    print("✓ Created 'apis.json' configuration file.")

# HELPER UTILITIES: ENV INTERPOLATION & SSL EXPIRY CHECK
def resolve_env_vars(data):
    """Recursively replaces ${VAR_NAME} or $VAR_NAME placeholders from os.environ."""
    if isinstance(data, str):
        def repl(match):
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, match.group(0))
        return re.sub(r"\$\{([A-Za-z0-9_]+)\}|\$([A-Za-z0-9_]+)", repl, data)
    elif isinstance(data, dict):
        return {k: resolve_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [resolve_env_vars(elem) for elem in data]
    return data

def check_ssl_expiry(url, min_valid_days=14, timeout=5):
    """
    Checks if HTTPS endpoint's SSL certificate is valid and not expiring soon.
    Returns (True, remaining_days) or (False, error_message).
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return True, "Not HTTPS"

    hostname = parsed.hostname
    port = parsed.port or 443

    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                not_after_str = cert.get("notAfter")
                if not not_after_str:
                    return False, "Could not read SSL notAfter date"
                
                # Format example: 'May 15 12:00:00 2026 GMT'
                expire_date = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                remaining_days = (expire_date - datetime.now(timezone.utc)).total_seconds() / 86400

                if remaining_days < 0:
                    return False, f"SSL Certificate expired {abs(int(remaining_days))} days ago"
                if remaining_days < min_valid_days:
                    return False, f"SSL Certificate expiring soon ({int(remaining_days)} days left < {min_valid_days} min)"
                
                return True, f"{int(remaining_days)} days"
    except Exception as e:
        return False, f"SSL check error: {str(e)}"

# SESSION SETUP & CHECKER FUNCTION
def create_session(pool_maxsize=20, max_retries=1):
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=0.3,
        status_forcelist=[502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(
        pool_connections=pool_maxsize,
        pool_maxsize=pool_maxsize,
        max_retries=retry_strategy
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def check_api(api, session=None):
    # Resolve any environment variables in the configuration dynamically
    api = resolve_env_vars(api)

    name = api["name"]
    url = api["url"]
    method = api.get("method", "GET").upper()
    headers = api.get("headers", {})
    params = api.get("params")
    body_data = api.get("data")
    body_json = api.get("json")
    expected_status = api.get("expected_status", 200)
    max_latency = api.get("max_latency_ms", 3000)
    expected_keys = api.get("expected_keys", [])
    expected_headers = api.get("expected_headers", {})
    timeout = api.get("timeout_s", 10)
    verify_ssl = api.get("verify_ssl", True)
    check_ssl_cert = api.get("check_ssl_cert", False)
    min_ssl_days = api.get("min_ssl_days", 14)

    # Auth configuration
    auth = None
    if "auth" in api:
        auth_conf = api["auth"]
        auth_type = auth_conf.get("type", "").lower()
        if auth_type == "basic":
            auth = HTTPBasicAuth(auth_conf.get("username", ""), auth_conf.get("password", ""))
        elif auth_type == "bearer":
            headers = dict(headers)
            headers["Authorization"] = f"Bearer {auth_conf.get('token', '')}"

    result = {
        "name": name,
        "method": method,
        "url": url,
        "passed": False,
        "status_code": "N/A",
        "latency_ms": 0,
        "error_message": ""
    }

    # Optional pre-check for SSL Certificate Expiry
    if check_ssl_cert and url.startswith("https://"):
        ssl_valid, ssl_msg = check_ssl_expiry(url, min_valid_days=min_ssl_days, timeout=timeout)
        if not ssl_valid:
            result["error_message"] = ssl_msg
            return result

    client = session or requests
    start_time = time.perf_counter()

    try:
        response = client.request(
            method=method,
            url=url,
            headers=headers if headers else None,
            params=params,
            data=body_data,
            json=body_json,
            auth=auth,
            verify=verify_ssl,
            timeout=timeout
        )
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        result["latency_ms"] = latency
        result["status_code"] = response.status_code

        # Status check (supports single int or list of acceptable codes)
        if isinstance(expected_status, list):
            if response.status_code not in expected_status:
                result["error_message"] = f"Expected HTTP status in {expected_status}, got {response.status_code}"
                return result
        elif response.status_code != expected_status:
            result["error_message"] = f"Expected HTTP {expected_status}, got {response.status_code}"
            return result

        # Latency check
        if latency > max_latency:
            result["error_message"] = f"Latency {latency}ms exceeded max {max_latency}ms"
            return result

        # Expected headers check (case-insensitive keys)
        if expected_headers:
            resp_headers_lower = {k.lower(): v for k, v in response.headers.items()}
            for exp_k, exp_v in expected_headers.items():
                val = resp_headers_lower.get(exp_k.lower())
                if val is None:
                    result["error_message"] = f"Missing expected response header '{exp_k}'"
                    return result
                if exp_v and exp_v.lower() not in val.lower():
                    result["error_message"] = f"Header '{exp_k}' expected '{exp_v}', got '{val}'"
                    return result

        # JSON keys check
        if expected_keys:
            try:
                body = response.json()
                if isinstance(body, list) and len(body) > 0:
                    body = body[0]
                
                if isinstance(body, dict):
                    missing = [k for k in expected_keys if k not in body]
                    if missing:
                        result["error_message"] = f"Missing JSON keys: {missing}"
                        return result
                else:
                    result["error_message"] = f"Expected JSON object or non-empty array, got {type(body).__name__}"
                    return result
            except Exception:
                result["error_message"] = "Response body is not valid JSON"
                return result

        result["passed"] = True

    except requests.exceptions.SSLError as e:
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        result["latency_ms"] = latency
        result["error_message"] = f"SSL Verification Error: {str(e)}"
    except requests.exceptions.Timeout:
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        result["latency_ms"] = latency
        result["error_message"] = f"Request timed out (>{timeout}s)"
    except requests.exceptions.ConnectionError:
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        result["latency_ms"] = latency
        result["error_message"] = "Connection failed / DNS error"
    except Exception as e:
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        result["latency_ms"] = latency
        result["error_message"] = str(e)

    return result

# 4. CSV AND HTML GENERATORS
def save_csv(results, filename="api_report.csv"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(filename)
    
    with open(filename, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "API Name", "Method", "Status", "Code", "Latency (ms)", "Error Message"])
        
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            writer.writerow([timestamp, r["name"], r.get("method", "GET"), status, r["status_code"], r["latency_ms"], r["error_message"]])

    print(f"✓ CSV report written to: {os.path.abspath(filename)}")

def save_html(results, filename="api_report.html"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    table_rows = "".join(
        f"""
        <tr>
            <td style="padding: 10px; border: 1px solid #ddd;">{r['name']}</td>
            <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; font-family: monospace;">{r.get('method', 'GET')}</td>
            <td style="padding: 10px; border: 1px solid #ddd;"><span style="color: white; background: {'#28a745' if r['passed'] else '#dc3545'}; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{'PASS' if r['passed'] else 'FAIL'}</span></td>
            <td style="padding: 10px; border: 1px solid #ddd;">{r['status_code']}</td>
            <td style="padding: 10px; border: 1px solid #ddd;">{r['latency_ms']} ms</td>
            <td style="padding: 10px; border: 1px solid #ddd; color: #b71c1c;">{r['error_message']}</td>
        </tr>
        """
        for r in results
    )

    html = f"""<!DOCTYPE html>
<html>
<head><title>API Health Report</title></head>
<body style="font-family: Arial, sans-serif; margin: 30px; background-color: #f7f9fa;">
    <h2>API Health Check Report</h2>
    <p><strong>Generated At:</strong> {timestamp}</p>
    <table style="width: 100%; border-collapse: collapse; background: white;">
        <tr style="background-color: #e9ecef; text-align: left;">
            <th style="padding: 10px; border: 1px solid #ddd;">API Name</th>
            <th style="padding: 10px; border: 1px solid #ddd;">Method</th>
            <th style="padding: 10px; border: 1px solid #ddd;">Status</th>
            <th style="padding: 10px; border: 1px solid #ddd;">Code</th>
            <th style="padding: 10px; border: 1px solid #ddd;">Latency</th>
            <th style="padding: 10px; border: 1px solid #ddd;">Error Details</th>
        </tr>
        {table_rows}
    </table>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ HTML report written to: {os.path.abspath(filename)}")

# 5. EXECUTION
def run_monitoring(config_file="apis.json", max_workers=10):
    print("\n--- Starting API Monitoring ---")
    
    with open(config_file, "r", encoding="utf-8") as f:
        endpoints = json.load(f)

    if not endpoints:
        print("No endpoints configured to monitor.")
        return

    # Use min(workers, endpoints count) to optimize resource allocation
    worker_count = min(max_workers, max(len(endpoints), 1))
    results = [None] * len(endpoints)

    with create_session(pool_maxsize=worker_count) as session:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            # Map future to original index to preserve config order in reports
            future_to_index = {
                executor.submit(check_api, item, session): idx
                for idx, item in enumerate(endpoints)
            }
            
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                res = future.result()
                results[idx] = res
                status_label = "PASS" if res["passed"] else "FAIL"
                method_label = res.get("method", "GET")
                print(f"Tested: [{method_label}] {res['name']} ... {status_label}")

    print("\n--- Saving Reports ---")
    save_csv(results, "api_report.csv")
    save_html(results, "api_report.html")

    print("\n--- Run Complete ---")

if __name__ == "__main__":
    run_monitoring()