"""
Feed each check in features/quality_checks.py deliberately bad input and confirm it
fires; feed it clean input and confirm it does not false-positive.
"""

import pandas as pd
import pytest

from features.quality_checks import (
    check_no_unexpected_nulls,
    check_positive_spend,
    check_customer_spine,
    check_recency_bounds,
    run_all_checks,
)


def _make_clean_features():
    """Create a clean feature DataFrame that should pass all checks."""
    return pd.DataFrame({
        "customer_id": list(range(1, 1501)),
        "tenure_days": [500] * 1500,
        "days_since_last_txn": [30] * 1500,
        "txn_count_lookback": [5] * 1500,
        "gross_spend_lookback": [250.0] * 1500,
        "avg_txn_value_lookback": [50.0] * 1500,
        "return_count_lookback": [0] * 1500,
        "active_months_12m": [6] * 1500,
        "as_of_date": pd.to_datetime(["2026-08-01"] * 1500),
    })


# ── check_no_unexpected_nulls ──

def test_null_check_fires_on_injected_null():
    features = _make_clean_features()
    features.loc[0, "tenure_days"] = None
    result = check_no_unexpected_nulls(features)
    assert not result["passed"]
    assert "tenure_days" in result["failing_features"]


def test_null_check_passes_on_clean_input():
    features = _make_clean_features()
    result = check_no_unexpected_nulls(features)
    assert result["passed"]


# ── check_positive_spend ──

def test_positive_spend_fires_on_negative_value():
    features = _make_clean_features()
    features.loc[5, "gross_spend_lookback"] = -50.0
    result = check_positive_spend(features)
    assert not result["passed"]


def test_positive_spend_passes_on_clean_input():
    features = _make_clean_features()
    result = check_positive_spend(features)
    assert result["passed"]


# ── check_customer_spine ──

def test_customer_spine_fires_on_wrong_count():
    features = _make_clean_features()
    small = features.iloc[:100].copy()
    result = check_customer_spine(small, expected_count=1500)
    assert not result["passed"]
    assert result["actual"] == 100


def test_customer_spine_passes_on_exact_match():
    features = _make_clean_features()
    result = check_customer_spine(features, expected_count=1500)
    assert result["passed"]


# ── check_recency_bounds ──

def test_recency_bounds_fires_on_negative():
    features = _make_clean_features()
    features.loc[0, "days_since_last_txn"] = -5
    result = check_recency_bounds(features)
    assert not result["passed"]


def test_recency_bounds_fires_when_exceeds_tenure():
    features = _make_clean_features()
    features.loc[0, "days_since_last_txn"] = 999
    features.loc[0, "tenure_days"] = 500
    result = check_recency_bounds(features)
    assert not result["passed"]


def test_recency_bounds_passes_on_clean_input():
    features = _make_clean_features()
    result = check_recency_bounds(features)
    assert result["passed"]


# ── run_all_checks ──

def test_checks_do_not_false_positive_on_clean_input():
    features = _make_clean_features()
    # run_all_checks should not raise
    result = run_all_checks(features)
    assert all(v["passed"] for v in result.values())


def test_run_all_raises_on_bad_input():
    features = _make_clean_features()
    features.loc[0, "gross_spend_lookback"] = -10.0
    with pytest.raises(ValueError, match="Data quality checks FAILED"):
        run_all_checks(features)