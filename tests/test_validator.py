import pytest
from api_monitor.validator import validate_json_body

def test_validate_json_empty():
    valid, err = validate_json_body("", {"id": "int"})
    assert not valid
    assert "empty" in err

def test_validate_json_malformed():
    valid, err = validate_json_body("{not-json", {"id": "int"})
    assert not valid
    assert "valid JSON" in err

def test_validate_json_success():
    body = '{"id": 1, "name": "Alice", "tags": ["a", "b"], "active": true, "score": 9.5, "meta": {"k": "v"}}'
    expected = {
        "id": "int",
        "name": "str",
        "tags": "list",
        "active": "bool",
        "score": "float",
        "meta": "dict"
    }
    valid, err = validate_json_body(body, expected)
    assert valid
    assert err is None

def test_validate_json_missing_key():
    body = '{"name": "Alice"}'
    valid, err = validate_json_body(body, {"id": "int", "name": "str"})
    assert not valid
    assert "missing key 'id'" in err

def test_validate_json_wrong_type():
    body = '{"id": "not-an-int"}'
    valid, err = validate_json_body(body, {"id": "int"})
    assert not valid
    assert "expected int, got str" in err

def test_validate_json_bool_not_int():
    # In python bool is subclass of int, but JSON specification treats them differently
    body = '{"id": true}'
    valid, err = validate_json_body(body, {"id": "int"})
    assert not valid
    assert "expected int, got bool" in err

def test_validate_json_array_of_objects():
    body = '[{"id": 1, "name": "item"}]'
    valid, err = validate_json_body(body, {"id": "int", "name": "str"})
    assert valid
    assert err is None
