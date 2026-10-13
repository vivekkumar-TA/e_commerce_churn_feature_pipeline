"""
The ONE shared feature-build entry point. Both `scripts/build_training_features.py`
(training path: a historical as-of date, batch of many customers) and
`scripts/score_customer.py` (scoring path: single customer_id, same as-of date) call this
same function — that is the entire train/score parity guarantee for this pipeline.

There must be exactly one code path here. The only difference between training and scoring
is which rows are selected at the end.
"""

import pandas as pd

from features import ingest, transforms


def build_features(
    as_of: str,
    source_paths: dict | None = None,
    customer_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Build the full feature set as of `as_of` for either the whole customer base
    (training path, `customer_ids=None`) or a specific subset (scoring path, one or more
    `customer_ids`).

    Parameters
    ----------
    as_of : str
        ISO-8601 date string for the as-of date. All temporal calculations enforce
        txn_timestamp <= as_of.
    source_paths : dict or None
        Dict with keys 'customers', 'transactions', 'monthly_agg' pointing to source paths.
        Defaults to standard data/ locations.
    customer_ids : list[int] or None
        If provided, filter output to only these customers (scoring path).
        If None, include all customers (training path).

    Returns
    -------
    pd.DataFrame
        One row per customer_id with columns: customer_id, as_of_date, and all features.
    """
    if source_paths is None:
        source_paths = {
            "customers": "data/customers.csv",
            "transactions": "data/transactions.db",
            "monthly_agg": "data/transactions_monthly_agg.parquet",
        }

    # ── Load all three sources ──
    customers = ingest.load_customers(source_paths["customers"])
    transactions = ingest.load_transactions(source_paths["transactions"])
    monthly_agg = ingest.load_monthly_agg(source_paths["monthly_agg"])

    # Filter to requested customer_ids if provided (the ONLY difference between
    # training and scoring paths)
    if customer_ids is not None:
        customers = customers[customers["customer_id"].isin(customer_ids)].copy()
        if customers.empty:
            raise ValueError(
                f"None of the requested customer_ids {customer_ids} were found "
                f"in customers.csv."
            )

    # ── Compute all features ──
    # Build features as a dict then concat — transforms return Series indexed by
    # customer_id, so pd.concat aligns them correctly.
    feature_dict = {}

    # Static / tenure features
    feature_dict["tenure_days"] = transforms.tenure_days(customers, as_of)

    # Recency
    feature_dict["days_since_last_txn"] = transforms.days_since_last_txn(
        customers, transactions, as_of
    )

    # Transaction count (30-day default version)
    feature_dict["txn_count_lookback"] = transforms.txn_count_lookback(
        customers, transactions, as_of, lookback_days=30
    )

    # Gross spend (30-day default version)
    feature_dict["gross_spend_lookback"] = transforms.gross_spend_lookback(
        customers, transactions, as_of, lookback_days=30
    )

    # Average transaction value (30-day)
    feature_dict["avg_txn_value_lookback"] = transforms.avg_txn_value_lookback(
        customers, transactions, as_of, lookback_days=30
    )

    # Return count (30-day)
    feature_dict["return_count_lookback"] = transforms.return_count_lookback(
        customers, transactions, as_of, lookback_days=30
    )

    # Engagement breadth — 12-month lookback from monthly aggregate
    feature_dict["active_months_12m"] = transforms.active_months_12m(
        customers, monthly_agg, as_of
    )

    # Assemble result — concat shares the customer_id index, then reset
    result = pd.concat(feature_dict, axis=1)
    result = result.reset_index()
    result = result.rename(columns={"index": "customer_id"})
    result["customer_id"] = result["customer_id"].astype(int)
    result["as_of_date"] = pd.Timestamp(as_of)

    # Reorder columns: customer_id first, then features, then as_of_date
    feature_cols = list(feature_dict.keys())
    result = result[["customer_id"] + feature_cols + ["as_of_date"]]

    return result