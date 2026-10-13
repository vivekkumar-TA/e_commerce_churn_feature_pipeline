"""
Runnable-standalone data-quality checks (null / outlier / row-count) against a built
features DataFrame, implementing every check listed in `feature_spec.md`'s data-quality
section.

Each check function returns a dict with "passed" (bool) and diagnostic info. All violations
raise exceptions when run through run_all_checks, per the "never just log a warning" rule.
"""

import pandas as pd

from features.schema import FEATURE_SCHEMA


def check_no_unexpected_nulls(features: pd.DataFrame) -> dict:
    """Fail if any feature column that should never be null (per schema.py) is null."""
    non_nullable = [fs.name for fs in FEATURE_SCHEMA if not fs.nullable]
    null_counts = features[non_nullable].isnull().sum()
    failing_features = null_counts[null_counts > 0]
    if len(failing_features) > 0:
        failing_rows = {}
        for col in failing_features.index:
            failing_rows[col] = features.index[features[col].isnull()].tolist()
        return {
            "passed": False,
            "failing_features": failing_features.to_dict(),
            "failing_rows": failing_rows,
        }
    return {"passed": True, "failing_features": [], "failing_rows": []}


def check_positive_spend(features: pd.DataFrame) -> dict:
    """Fail if gross_spend_lookback has any negative values (indicates unfiltered returns)."""
    if "gross_spend_lookback" not in features.columns:
        return {"passed": True, "message": "gross_spend_lookback not in features, skipping"}
    negative = features["gross_spend_lookback"] < 0
    if negative.any():
        return {
            "passed": False,
            "failing_features": {"gross_spend_lookback": negative.sum()},
            "failing_rows": {"gross_spend_lookback": features.index[negative].tolist()},
        }
    return {"passed": True, "failing_features": [], "failing_rows": []}


def check_customer_spine(features: pd.DataFrame, expected_count: int = 1500) -> dict:
    """Fail if output row count does not match the expected customer count.

    Default 1,500 matches customers.csv.
    """
    actual = len(features)
    if actual != expected_count:
        return {
            "passed": False,
            "expected": expected_count,
            "actual": actual,
            "diff": actual - expected_count,
        }
    return {"passed": True, "expected": expected_count, "actual": actual}


def check_recency_bounds(features: pd.DataFrame) -> dict:
    """Fail if days_since_last_txn is negative or exceeds tenure_days.

    Negative indicates future transaction leakage.
    Exceeding tenure_days indicates timestamp corruption.
    """
    if "days_since_last_txn" not in features.columns or "tenure_days" not in features.columns:
        return {"passed": True, "message": "recency/tenure columns not present, skipping"}
    negatives = features["days_since_last_txn"] < 0
    exceeds_tenure = features["days_since_last_txn"] > features["tenure_days"]
    if negatives.any() or exceeds_tenure.any():
        issues = {}
        if negatives.any():
            issues["negative_recency"] = features.index[negatives].tolist()
        if exceeds_tenure.any():
            issues["exceeds_tenure"] = features.index[exceeds_tenure].tolist()
        return {"passed": False, "issues": issues}
    return {"passed": True, "issues": {}}


def run_all_checks(features: pd.DataFrame) -> dict:
    """Run every check above and raise on first failure.

    Returns a combined summary dict if all pass.
    Raises ValueError on any failure (never just logs a warning).
    """
    checks = [
        ("check_null_features", check_no_unexpected_nulls(features)),
        ("check_positive_spend", check_positive_spend(features)),
        ("check_customer_spine", check_customer_spine(features)),
        ("check_recency_bounds", check_recency_bounds(features)),
    ]

    failures = []
    for name, result in checks:
        if not result["passed"]:
            failures.append((name, result))

    if failures:
        msg_lines = ["Data quality checks FAILED:"]
        for name, result in failures:
            msg_lines.append(f"  - {name}: {result}")
        raise ValueError("\n".join(msg_lines))

    return {name: result for name, result in checks}