"""
Versioned output feature schema: the authoritative list of every feature this pipeline
produces, with dtype, nullability, source(s), and feature-set version.

`nullable` is False for every feature because the pipeline applies explicit zero-activity
defaults. Consumers (FEATURE_LINEAGE.md generation, feature store registration) read from
this list.
"""

from dataclasses import dataclass


@dataclass
class FeatureSpec:
    name: str
    dtype: str
    nullable: bool
    source: str
    feature_set_version: str


FEATURE_SCHEMA: list[FeatureSpec] = [
    FeatureSpec(
        name="tenure_days",
        dtype="int64",
        nullable=False,
        source="customers.csv",
        feature_set_version="1.0.0",
    ),
    FeatureSpec(
        name="days_since_last_txn",
        dtype="int64",
        nullable=False,
        source="transactions.db",
        feature_set_version="1.0.0",
    ),
    FeatureSpec(
        name="txn_count_lookback",
        dtype="int64",
        nullable=False,
        source="transactions.db",
        feature_set_version="1.0.0",
    ),
    FeatureSpec(
        name="gross_spend_lookback",
        dtype="float64",
        nullable=False,
        source="transactions.db",
        feature_set_version="1.0.0",
    ),
    FeatureSpec(
        name="avg_txn_value_lookback",
        dtype="float64",
        nullable=False,
        source="transactions.db",
        feature_set_version="1.0.0",
    ),
    FeatureSpec(
        name="return_count_lookback",
        dtype="int64",
        nullable=False,
        source="transactions.db",
        feature_set_version="1.0.0",
    ),
    FeatureSpec(
        name="active_months_12m",
        dtype="int64",
        nullable=False,
        source="transactions_monthly_agg.parquet",
        feature_set_version="1.0.0",
    ),
]