"""
One pure function per candidate feature named in `feature_spec.md`.

Each function:
- Is independent of any I/O (takes already-loaded DataFrames in, returns a Series/DataFrame out).
- Handles the zero-activity case explicitly, per the default the spec states.
- Only touches the source(s) the spec names for that feature.

IMPORTANT: All functions return a Series indexed by `customer_id` values
(e.g. index = [1, 2, 5, 99]). Callers must use index alignment (pd.concat)
or convert with .reset_index(drop=True) for positional assignment.
"""

import numpy as np
import pandas as pd


def _reindex_to_customers(series: pd.Series, customers: pd.DataFrame, fill_value=0):
    """Reindex a grouped-by-customer_id series to cover all customers in order."""
    return series.reindex(customers["customer_id"], fill_value=fill_value)


def tenure_days(
    customers: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Compute customer tenure in days as of `as_of`."""
    as_of_date = pd.Timestamp(as_of)
    diff = (as_of_date - customers["signup_date"]).dt.days
    diff.index = customers["customer_id"]
    return diff


def days_since_last_txn(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Days since the customer's last transaction before as_of.

    Zero-activity customers default to their full tenure.
    """
    as_of_date = pd.Timestamp(as_of)
    tenures = tenure_days(customers, as_of)

    # Filter transactions to those before as_of
    valid = transactions[transactions["txn_timestamp"] <= as_of_date]

    # Find last transaction timestamp per customer
    last_txn = valid.groupby("customer_id")["txn_timestamp"].max()
    if last_txn.empty:
        return tenures.copy()

    last_txn = (as_of_date - last_txn).dt.days
    result = _reindex_to_customers(last_txn, customers, fill_value=0)

    # Fill zero-activity customers with their tenure
    zero_mask = result == 0
    result[zero_mask] = tenures[zero_mask]

    return result


def txn_count_lookback(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    lookback_days: int,
) -> pd.Series:
    """Count of non-returned transactions in the lookback window before as_of.

    Zero-activity customers default to 0.
    """
    as_of_date = pd.Timestamp(as_of)
    window_start = as_of_date - pd.Timedelta(days=lookback_days)

    valid = transactions[
        (transactions["txn_timestamp"] >= window_start)
        & (transactions["txn_timestamp"] <= as_of_date)
        & (transactions["is_returned"] == 0)
    ]
    if valid.empty:
        return pd.Series(0, index=customers["customer_id"], dtype=int)

    counts = valid.groupby("customer_id").size()
    result = _reindex_to_customers(counts, customers, fill_value=0)
    return result.astype(int)


def gross_spend_lookback(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    lookback_days: int,
) -> pd.Series:
    """Sum of non-returned transaction amounts in the lookback window before as_of.

    Zero-activity customers default to 0.0.
    """
    as_of_date = pd.Timestamp(as_of)
    window_start = as_of_date - pd.Timedelta(days=lookback_days)

    valid = transactions[
        (transactions["txn_timestamp"] >= window_start)
        & (transactions["txn_timestamp"] <= as_of_date)
        & (transactions["is_returned"] == 0)
    ]
    if valid.empty:
        return pd.Series(0.0, index=customers["customer_id"], dtype=float)

    spend = valid.groupby("customer_id")["amount"].sum()
    result = _reindex_to_customers(spend, customers, fill_value=0.0)
    return result


def avg_txn_value_lookback(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    lookback_days: int,
) -> pd.Series:
    """Average transaction value for non-returned purchases in the lookback window.

    Formula: gross_spend_lookback / purchase_count (both from non-returned only).
    Zero-activity customers and zero-purchase windows default to 0.0.
    Zero-division guard: returns 0.0 when purchase_count is 0.
    """
    spend = gross_spend_lookback(customers, transactions, as_of, lookback_days)
    count = txn_count_lookback(customers, transactions, as_of, lookback_days)

    # Zero-division guard: where count is 0, ATV is 0.0
    result = np.where(count == 0, 0.0, spend / count)
    return pd.Series(result, index=customers["customer_id"], dtype=float)


def return_count_lookback(
    customers: pd.DataFrame,
    transactions: pd.DataFrame,
    as_of: str,
    lookback_days: int,
) -> pd.Series:
    """Count of returned transactions in the lookback window before as_of.

    Zero-activity customers default to 0.
    """
    as_of_date = pd.Timestamp(as_of)
    window_start = as_of_date - pd.Timedelta(days=lookback_days)

    valid = transactions[
        (transactions["txn_timestamp"] >= window_start)
        & (transactions["txn_timestamp"] <= as_of_date)
        & (transactions["is_returned"] == 1)
    ]
    if valid.empty:
        return pd.Series(0, index=customers["customer_id"], dtype=int)

    counts = valid.groupby("customer_id").size()
    result = _reindex_to_customers(counts, customers, fill_value=0)
    return result.astype(int)


def active_months_12m(
    customers: pd.DataFrame,
    monthly_agg: pd.DataFrame,
    as_of: str,
) -> pd.Series:
    """Count of distinct calendar months with activity in the last 365 days before as_of.

    Reads from the monthly aggregate parquet.
    Zero-activity customers default to 0.
    """
    as_of_date = pd.Timestamp(as_of)
    window_start = as_of_date - pd.Timedelta(days=365)

    valid = monthly_agg[
        (monthly_agg["txn_month"] >= window_start)
        & (monthly_agg["txn_month"] <= as_of_date)
    ]
    if valid.empty:
        return pd.Series(0, index=customers["customer_id"], dtype=int)

    months = valid.groupby("customer_id")["txn_month"].nunique()
    result = _reindex_to_customers(months, customers, fill_value=0)
    return result.astype(int)