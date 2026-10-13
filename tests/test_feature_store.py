"""
For each feature that feature_spec.md designates as versioned (gross_spend_lookback and
txn_count_lookback), register its versions, confirm each is independently retrievable,
confirm is_latest correctly identifies the highest version, and confirm list_versions
returns distinct parquet_path values that all exist on disk.

All store operations are isolated inside pytest's tmp_path — the production
feature_store/ directory is never touched.
"""

from pathlib import Path

import pandas as pd
import pytest

import feature_store.store as store
from feature_store.store import (
    register_version,
    get_latest,
    get_version,
    list_versions,
)


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path):
    """Point store paths at a temp directory so tests never touch production data."""
    monkeypatch.setattr(store, "REGISTRY_DB", str(tmp_path / "registry.db"))
    monkeypatch.setattr(store, "VALUES_DIR", str(tmp_path / "values"))


def _make_feature_df(feature_name: str, value_col: str = None):
    """Create a simple feature DataFrame for testing."""
    if value_col is None:
        value_col = feature_name
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        value_col: [10.0, 20.0, 30.0],
        "as_of_date": pd.to_datetime(["2026-08-01"] * 3),
    })


class TestGrossSpendLookback:
    FEATURE = "gross_spend_lookback"

    def test_register_and_retrieve_v1_and_v2(self):
        df1 = _make_feature_df(self.FEATURE)
        v1 = register_version(
            feature_name=self.FEATURE,
            values_df=df1,
            description="30-day lookback",
            source_columns="transactions.db: amount, txn_timestamp",
            transform_summary="SUM(amount) WHERE is_returned=0 AND txn_timestamp within 30d",
            business_rationale="Short-term monetary velocity",
            parameters={"lookback_days": 30},
        )
        assert v1 == 1

        # Register v2 (60-day)
        df2 = _make_feature_df(self.FEATURE)
        df2[self.FEATURE] = [25.0, 35.0, 50.0]  # different values
        v2 = register_version(
            feature_name=self.FEATURE,
            values_df=df2,
            description="60-day lookback",
            source_columns="transactions.db: amount, txn_timestamp",
            transform_summary="SUM(amount) WHERE is_returned=0 AND txn_timestamp within 60d",
            business_rationale="Medium-term spend baseline",
            parameters={"lookback_days": 60},
        )
        assert v2 == 2

        # Retrieve each by version
        loaded_v1 = get_version(self.FEATURE, 1)
        assert loaded_v1[self.FEATURE].iloc[0] == 10.0
        loaded_v2 = get_version(self.FEATURE, 2)
        assert loaded_v2[self.FEATURE].iloc[0] == 25.0

    def test_is_latest_points_to_highest_version(self):
        df1 = _make_feature_df(self.FEATURE)
        register_version(
            feature_name=self.FEATURE, values_df=df1,
            description="v1", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={},
        )
        df2 = _make_feature_df(self.FEATURE)
        df2[self.FEATURE] = [99.0, 99.0, 99.0]
        register_version(
            feature_name=self.FEATURE, values_df=df2,
            description="v2", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={},
        )
        latest = get_latest(self.FEATURE)
        assert latest[self.FEATURE].iloc[0] == 99.0  # v2 values

    def test_list_versions_returns_distinct_parquet_paths(self):
        df1 = _make_feature_df(self.FEATURE)
        register_version(
            feature_name=self.FEATURE, values_df=df1,
            description="v1", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={},
        )
        df2 = _make_feature_df(self.FEATURE)
        register_version(
            feature_name=self.FEATURE, values_df=df2,
            description="v2", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={"lookback_days": 60},
        )

        versions = list_versions(self.FEATURE)
        assert len(versions) == 2
        paths = versions["parquet_path"].tolist()
        assert len(set(paths)) == 2  # distinct
        for p in paths:
            assert Path(p).exists()  # actually exist on disk


class TestTxnCountLookback:
    FEATURE = "txn_count_lookback"

    def test_register_and_retrieve_v1_and_v2(self):
        df1 = _make_feature_df(self.FEATURE, value_col=self.FEATURE)
        df1[self.FEATURE] = df1[self.FEATURE].astype(int)
        v1 = register_version(
            feature_name=self.FEATURE,
            values_df=df1,
            description="30-day window",
            source_columns="transactions.db: txn_timestamp",
            transform_summary="COUNT(txn_id) WHERE is_returned=0 AND within 30d",
            business_rationale="Short-term purchase frequency",
            parameters={"window_days": 30},
        )
        assert v1 == 1

        df2 = _make_feature_df(self.FEATURE, value_col=self.FEATURE)
        df2[self.FEATURE] = [5, 8, 12]
        v2 = register_version(
            feature_name=self.FEATURE,
            values_df=df2,
            description="90-day window",
            source_columns="transactions.db: txn_timestamp",
            transform_summary="COUNT(txn_id) WHERE is_returned=0 AND within 90d",
            business_rationale="Quarterly purchase cadence",
            parameters={"window_days": 90},
        )
        assert v2 == 2

        loaded_v1 = get_version(self.FEATURE, 1)
        assert loaded_v1[self.FEATURE].iloc[0] == 10
        loaded_v2 = get_version(self.FEATURE, 2)
        assert loaded_v2[self.FEATURE].iloc[0] == 5

    def test_is_latest_points_to_highest_version(self):
        df1 = _make_feature_df(self.FEATURE, value_col=self.FEATURE)
        df1[self.FEATURE] = df1[self.FEATURE].astype(int)
        register_version(
            feature_name=self.FEATURE, values_df=df1,
            description="v1", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={},
        )
        df2 = _make_feature_df(self.FEATURE, value_col=self.FEATURE)
        df2[self.FEATURE] = [100, 100, 100]
        register_version(
            feature_name=self.FEATURE, values_df=df2,
            description="v2", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={"window_days": 90},
        )
        latest = get_latest(self.FEATURE)
        assert latest[self.FEATURE].iloc[0] == 100

    def test_list_versions_returns_distinct_parquet_paths(self):
        df1 = _make_feature_df(self.FEATURE, value_col=self.FEATURE)
        df1[self.FEATURE] = df1[self.FEATURE].astype(int)
        register_version(
            feature_name=self.FEATURE, values_df=df1,
            description="v1", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={},
        )
        df2 = _make_feature_df(self.FEATURE, value_col=self.FEATURE)
        df2[self.FEATURE] = [0, 0, 0]
        register_version(
            feature_name=self.FEATURE, values_df=df2,
            description="v2", source_columns="x",
            transform_summary="y", business_rationale="z",
            parameters={"window_days": 90},
        )
        versions = list_versions(self.FEATURE)
        assert len(versions) == 2
        paths = versions["parquet_path"].tolist()
        assert len(set(paths)) == 2
        for p in paths:
            assert Path(p).exists()