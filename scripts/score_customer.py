#!/usr/bin/env python3
"""
Builds features for one or more specific customer_ids as of a given date, using the
scoring path of the same shared build_features(as_of, ...) entry point used by
build_training_features.py.

Usage:
    python scripts/score_customer.py --customer-id 42 --customer-id 58 --as-of 2026-08-01
"""

import argparse
import sys

from features.build import build_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--customer-id",
        type=int,
        action="append",
        required=True,
        help="Customer ID to score. May be passed multiple times.",
    )
    parser.add_argument(
        "--as-of",
        default="2026-08-01",
        help="As-of date for feature computation (default: 2026-08-01).",
    )
    args = parser.parse_args()

    customer_ids = args.customer_id
    print(f"Scoring features for customer(s) {customer_ids} as of {args.as_of}...")

    # Call the SAME shared entry point as build_training_features.py.
    # The only difference: we pass customer_ids to filter.
    features = build_features(as_of=args.as_of, customer_ids=customer_ids)

    if features.empty:
        print(f"  No data returned for customer(s) {customer_ids}.")
        sys.exit(1)

    for _, row in features.iterrows():
        print(f"\n  Customer {int(row['customer_id'])}:")
        for col in features.columns:
            if col in ("customer_id", "as_of_date"):
                continue
            print(f"    {col}: {row[col]}")


if __name__ == "__main__":
    main()