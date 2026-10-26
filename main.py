import csv
import json
import os
import time
import requests

# -------------------------------------------------------------
# 1. SETUP TEST CONFIGURATION DIRECTLY
# -------------------------------------------------------------
CONFIG_DATA = []

# Ensure 'apis.json' exists locally
if not os.path.exists("apis.json"):
    with open("apis.json", "w", encoding="utf-8") as f:
        json.dump(CONFIG_DATA, f, indent=2)
    print("✓ Created 'apis.json' configuration file.")

# -------------------------------------------------------------
# 2. CHECKER FUNCTION
# -------------------------------------------------------------
def check_api(api):
    name = api["name"]
    url = api["url"]
    expected_status = api.get("expected_status", 200)
    max_latency = api.get("max_latency_ms", 3000)
    expected_keys = api.get("expected_keys", [])

    result = {
        "name": name,
        "url": url,
        "passed": False,
        "status_code": "N/A",
        "latency_ms": 0,
        "error_message": ""
    }

    try:
        response = requests.get(url, timeout=10)
        latency = round(response.elapsed.total_seconds() * 1000, 2)
        result["latency_ms"] = latency
        result["status_code"] = response.status_code

        # Status check
        if response.status_code != expected_status:
            result["error_message"] = f"Expected HTTP {expected_status}, got {response.status_code}"
            return result

        # Latency check
        if latency > max_latency:
            result["error_message"] = f"Latency {latency}ms exceeded max {max_latency}ms"
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
            except Exception:
                result["error_message"] = "Response body is not valid JSON"
                return result

        result["passed"] = True

    except requests.exceptions.Timeout:
        result["error_message"] = "Request timed out (>10s)"
    except requests.exceptions.ConnectionError:
        result["error_message"] = "Connection failed / DNS error"
    except Exception as e:
        result["error_message"] = str(e)

    return result

# -------------------------------------------------------------
# 3. CSV AND HTML GENERATORS
# -------------------------------------------------------------
def save_csv(results, filename="api_report.csv"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(filename)
    
    with open(filename, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "API Name", "Status", "Code", "Latency (ms)", "Error Message"])
        
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            writer.writerow([timestamp, r["name"], status, r["status_code"], r["latency_ms"], r["error_message"]])

    print(f"✓ CSV report written to: {os.path.abspath(filename)}")

def save_html(results, filename="api_report.html"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    table_rows = ""

    for r in results:
        status_color = "#28a745" if r["passed"] else "#dc3545"
        status_text = "PASS" if r["passed"] else "FAIL"

        table_rows += f"""
        <tr>
            <td style="padding: 10px; border: 1px solid #ddd;">{r['name']}</td>
            <td style="padding: 10px; border: 1px solid #ddd;"><span style="color: white; background: {status_color}; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{status_text}</span></td>
            <td style="padding: 10px; border: 1px solid #ddd;">{r['status_code']}</td>
            <td style="padding: 10px; border: 1px solid #ddd;">{r['latency_ms']} ms</td>
            <td style="padding: 10px; border: 1px solid #ddd; color: #b71c1c;">{r['error_message']}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head><title>API Health Report</title></head>
<body style="font-family: Arial, sans-serif; margin: 30px; background-color: #f7f9fa;">
    <h2>API Health Check Report</h2>
    <p><strong>Generated At:</strong> {timestamp}</p>
    <table style="width: 100%; border-collapse: collapse; background: white;">
        <tr style="background-color: #e9ecef; text-align: left;">
            <th style="padding: 10px; border: 1px solid #ddd;">API Name</th>
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

# -------------------------------------------------------------
# 4. EXECUTION
# -------------------------------------------------------------
if __name__ == "__main__":
    print("\n--- Starting API Monitoring ---")
    
    with open("apis.json", "r", encoding="utf-8") as f:
        endpoints = json.load(f)

    all_results = []
    for item in endpoints:
        print(f"Testing: {item['name']} ... ", end="", flush=True)
        res = check_api(item)
        all_results.append(res)
        print("PASS" if res["passed"] else "FAIL")

    print("\n--- Saving Reports ---")
    save_csv(all_results, "api_report.csv")
    save_html(all_results, "api_report.html")

    print("\n--- Run Complete ---")