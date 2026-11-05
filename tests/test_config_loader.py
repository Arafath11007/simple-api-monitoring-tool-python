import pytest
from pathlib import Path
from api_monitor.config_loader import load_config
from api_monitor.exceptions import ConfigError

def test_load_valid_config(tmp_path):
    conf_file = tmp_path / "valid.yaml"
    conf_file.write_text("""
settings:
  default_timeout_seconds: 5
  slow_threshold_ms: 1000
endpoints:
  - name: Test API
    url: https://example.com/api
    method: GET
    expected_status: 200
    expected_json:
      key: str
    enabled: true
alerts:
  slack:
    enabled: true
""")
    config = load_config(conf_file)
    assert config.settings.default_timeout_seconds == 5
    assert len(config.endpoints) == 1
    assert config.endpoints[0].name == "Test API"
    assert config.alerts.slack.enabled is True

def test_missing_config():
    with pytest.raises(ConfigError):
        load_config("non_existent_file.yaml")

def test_invalid_url_scheme(tmp_path):
    conf_file = tmp_path / "invalid_url.yaml"
    conf_file.write_text("""
endpoints:
  - name: Bad URL
    url: ftp://invalid.example.com
""")
    with pytest.raises(ConfigError) as exc_info:
        load_config(conf_file)
    assert "invalid URL scheme" in str(exc_info.value)

def test_duplicate_endpoint_names(tmp_path):
    conf_file = tmp_path / "duplicate.yaml"
    conf_file.write_text("""
endpoints:
  - name: Duplicate API
    url: https://example.com/1
  - name: Duplicate API
    url: https://example.com/2
""")
    with pytest.raises(ConfigError) as exc_info:
        load_config(conf_file)
    assert "Duplicate endpoint name" in str(exc_info.value)

def test_invalid_json_type(tmp_path):
    conf_file = tmp_path / "bad_type.yaml"
    conf_file.write_text("""
endpoints:
  - name: API
    url: https://example.com
    expected_json:
      val: unknown_type
""")
    with pytest.raises(ConfigError) as exc_info:
        load_config(conf_file)
    assert "invalid expected_json type" in str(exc_info.value)
