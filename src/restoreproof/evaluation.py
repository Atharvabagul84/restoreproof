"""Pure policy decisions; execution and SQL permissions live in the adapter."""
from __future__ import annotations

from datetime import timezone

from .contract import Check, Freshness, is_finite_json, parse_timestamp


def _strict_equal(expected: object, actual: object) -> bool:
    if type(expected) is not type(actual):
        return False
    if type(expected) is dict:
        return expected.keys() == actual.keys() and all(_strict_equal(value, actual[key]) for key, value in expected.items())
    if type(expected) is list:
        return len(expected) == len(actual) and all(_strict_equal(left, right) for left, right in zip(expected, actual))
    return expected == actual


def evaluate_check(spec: Check, actual: object) -> dict:
    """Compare JSON recursively without Python's bool/int coercive equality."""
    valid = is_finite_json(actual)
    result = {
        "name": spec.name,
        "status": "PASS" if valid and _strict_equal(spec.expected, actual) else "FAIL",
        "expected": spec.expected,
        "actual": actual if valid else None,
    }
    if not valid:
        result["reason"] = "actual_value_is_not_finite_json"
    return result


def evaluate_freshness(spec: Freshness, actual: object) -> dict:
    """Evaluate recovered watermark age; absent/invalid evidence is incomplete."""
    incident = spec.incident_at.astimezone(timezone.utc)
    result = {
        "name": "freshness",
        "status": "INCOMPLETE",
        "incident_at": incident.isoformat(),
        "recovered_at": None,
        "age_seconds": None,
        "max_data_age_seconds": spec.max_data_age_seconds,
        "reason": "watermark_missing" if actual is None else "watermark_invalid",
    }
    try:
        recovered = parse_timestamp(actual).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return result
    result["recovered_at"] = recovered.isoformat()
    age = (incident - recovered).total_seconds()
    if age < 0:
        result["reason"] = "watermark_after_incident"
        return result
    result["age_seconds"] = age
    result["status"] = "PASS" if age <= spec.max_data_age_seconds else "FAIL"
    result["reason"] = "within_policy" if result["status"] == "PASS" else "watermark_too_old"
    return result
