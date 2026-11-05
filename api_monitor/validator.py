"""JSON response schema and type validation."""

import json
from typing import Any

TYPE_MAPPING = {
    "str": str,
    "int": int,
    "float": (float, int),  # int is acceptable for float numbers in JSON
    "bool": bool,
    "list": list,
    "dict": dict,
}


def validate_json_body(raw_text: str, expected_json: dict[str, str]) -> tuple[bool, str | None]:
    """
    Parses raw_text as JSON and validates expected keys and their types.
    Returns (True, None) if valid, or (False, reason) if invalid.
    """
    if not raw_text.strip():
        return False, "Response body is empty, expected JSON"

    try:
        data = json.loads(raw_text)
    except Exception:
        return False, "Response body is not valid JSON"

    # If the root element is a list, inspect the first item if available
    target = data
    if isinstance(data, list):
        if len(data) == 0:
            if expected_json:
                return False, "Response is an empty array; cannot validate expected keys"
            return True, None
        target = data[0]

    if not isinstance(target, dict):
        if expected_json:
            return False, f"Expected JSON object or array of objects, got {type(target).__name__}"
        return True, None

    problems: list[str] = []

    for key, type_str in expected_json.items():
        if key not in target:
            problems.append(f"missing key '{key}'")
            continue

        expected_type = TYPE_MAPPING.get(type_str)
        val = target[key]

        # In Python bool is a subclass of int (bool is int -> True).
        # We must explicitly ensure int isn't satisfied by a bool.
        if type_str == "int" and isinstance(val, bool):
            problems.append(f"key '{key}' expected int, got bool")
        elif expected_type and not isinstance(val, expected_type):
            problems.append(f"key '{key}' expected {type_str}, got {type(val).__name__}")

    if problems:
        return False, f"JSON validation failed: {', '.join(problems)}"

    return True, None
