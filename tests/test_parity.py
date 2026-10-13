"""
The parity test: build features for the same customer via the "training" path (batch)
and via the "scoring" path (single customer), same as_of, and assert every feature
value is identical.
"""

import pandas as pd
import pytest

from features.build import build_features


AS_OF = "2026-08-01"


def test_training_and_scoring_paths_agree_for_same_customer():
    """Training path (batch) and scoring path (single customer) must produce identical
    feature values for the same customer_id and as_of date."""
    # Training path: build all customers
    batch = build_features(as_of=AS_OF)

    # Pick a few customers with very different activity profiles
    test_ids = [1, 2, 58, 100, 500]

    for cid in test_ids:
        # Scoring path: single customer via customer_ids filter
        single = build_features(as_of=AS_OF, customer_ids=[cid])

        batch_row = batch[batch["customer_id"] == cid]
        assert len(batch_row) == 1, f"Customer {cid} not found in batch output"
        assert len(single) == 1, f"Customer {cid} not found in scoring output"

        # Compare every feature column (exclude customer_id and as_of_date)
        feature_cols = [c for c in batch.columns if c not in ("customer_id", "as_of_date")]

        for col in feature_cols:
            bval = batch_row[col].iloc[0]
            sval = single[col].iloc[0]
            if isinstance(bval, float):
                assert bval == pytest.approx(sval, abs=1e-6), (
                    f"Mismatch for customer {cid}, feature '{col}': "
                    f"batch={bval}, scoring={sval}"
                )
            else:
                assert bval == sval, (
                    f"Mismatch for customer {cid}, feature '{col}': "
                    f"batch={bval}, scoring={sval}"
                )


def test_parity_zero_activity_customer():
    """A zero-activity customer (customer 1) must have identical values in both paths."""
    batch = build_features(as_of=AS_OF)
    single = build_features(as_of=AS_OF, customer_ids=[1])

    batch_row = batch[batch["customer_id"] == 1]
    feature_cols = [c for c in batch.columns if c not in ("customer_id", "as_of_date")]

    for col in feature_cols:
        bval = batch_row[col].iloc[0]
        sval = single[col].iloc[0]
        if isinstance(bval, float):
            assert bval == pytest.approx(sval, abs=1e-6)
        else:
            assert bval == sval