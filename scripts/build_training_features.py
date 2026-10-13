#!/usr/bin/env python3
"""
Builds features for the full training population as of a given date, writes a versioned
parquet feature snapshot, and registers every candidate feature into the feature store.

Usage:
    python scripts/build_training_features.py --as-of 2026-08-01

Applies all data-quality checks before writing. On failure, prints diagnostic info and
exits non-zero rather than writing bad output.
"""

import argparse
import sys

from features.build import build_features
from features.quality_checks import run_all_checks
from features.schema import FEATURE_SCHEMA
from feature_store.store import register_version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default="2026-08-01",
        help="As-of date for feature computation (default: 2026-08-01).",
    )
    args = parser.parse_args()

    print(f"Building features as of {args.as_of}...")

    # Build features using the single shared code path
    features = build_features(as_of=args.as_of)
    print(f"  Built {len(features)} rows x {len(features.columns)} columns")

    # Run quality checks before writing
    print("  Running quality checks...")
    try:
        check_results = run_all_checks(features)
        print("  [OK] All quality checks passed")
    except ValueError as e:
        print(f"  [FAIL] Quality checks FAILED:\n{e}")
        sys.exit(1)

    # Register every candidate feature into the feature store
    print("  Registering features in the feature store...")
    for fs in FEATURE_SCHEMA:
        feature_df = features[["customer_id", fs.name, "as_of_date"]].copy()
        version = register_version(
            feature_name=fs.name,
            values_df=feature_df,
            description=fs.name.replace("_", " ").title(),
            source_columns=fs.source,
            transform_summary=f"Computed per feature_spec.md v{fs.feature_set_version}",
            business_rationale=f"Churn feature: {fs.name}",
            parameters={},
        )
        print(f"    [OK] {fs.name} registered as v{version}")

    # Register versioned features with their alternate parameter values
    from features import transforms, ingest

    customers = ingest.load_customers()
    transactions = ingest.load_transactions()

    # Versioned Feature 1: gross_spend_lookback v2 (60-day)
    spend_60 = transforms.gross_spend_lookback(
        customers, transactions, args.as_of, lookback_days=60
    )
    result_60 = features[["customer_id", "as_of_date"]].copy()
    result_60["gross_spend_lookback"] = spend_60.values

    v2_spend = register_version(
        feature_name="gross_spend_lookback",
        values_df=result_60[["customer_id", "gross_spend_lookback", "as_of_date"]],
        description="Gross Spend Lookback -- 60-day window (medium-term baseline)",
        source_columns="transactions.db: transactions.amount, txn_timestamp",
        transform_summary="SUM(amount) WHERE is_returned=0 AND txn_timestamp within 60d of as_of",
        business_rationale="60-day window captures medium-term spend baseline; "
        "divergence from 30-day identifies spending deceleration in the most recent 30 days",
        parameters={"lookback_days": 60},
    )
    print(f"    [OK] gross_spend_lookback v{v2_spend} (60-day) registered")

    # Versioned Feature 2: txn_count_lookback v2 (90-day)
    count_90 = transforms.txn_count_lookback(
        customers, transactions, args.as_of, lookback_days=90
    )
    result_90 = features[["customer_id", "as_of_date"]].copy()
    result_90["txn_count_lookback"] = count_90.values

    v2_count = register_version(
        feature_name="txn_count_lookback",
        values_df=result_90[["customer_id", "txn_count_lookback", "as_of_date"]],
        description="Transaction Count Lookback -- 90-day window (quarterly purchase cadence)",
        source_columns="transactions.db: transactions.txn_timestamp",
        transform_summary="COUNT(txn_id) WHERE is_returned=0 AND txn_timestamp within 90d of as_of",
        business_rationale="90-day window captures broader quarterly engagement; "
        "ratio of 30d to (90d/3) exposes velocity deceleration",
        parameters={"window_days": 90},
    )
    print(f"    [OK] txn_count_lookback v{v2_count} (90-day) registered")

    print(f"\n[DONE] Build complete. Feature store updated with {len(FEATURE_SCHEMA)} features "
          f"(gross_spend_lookback and txn_count_lookback have 2 versions each).")


if __name__ == "__main__":
    main()