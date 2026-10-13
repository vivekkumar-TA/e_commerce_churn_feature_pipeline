"""
Tests for each feature function in features/transforms.py, in isolation.

Per skill.md: each feature needs a normal case, a zero-activity case, a single-record
case, and (where relevant) a case at a time-window boundary.
"""

import pandas as pd
import pytest

from features import transforms


@pytest.fixture
def customers():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "signup_date": pd.to_datetime(["2024-01-15", "2025-06-01", "2025-01-01"]),
        "acquisition_channel": ["organic", "paid_search", "referral"],
        "region": ["east", "north", "west"],
        "churned": [0, 1, 0],
    })


@pytest.fixture
def transactions():
    return pd.DataFrame({
        "customer_id": [2, 2, 2, 2],
        "txn_timestamp": pd.to_datetime([
            "2026-07-01",
            "2026-07-15",
            "2026-06-01",
            "2026-05-01",
        ]),
        "category": ["grocery", "electronics", "home", "sports"],
        "channel": ["web", "mobile_app", "store", "web"],
        "amount": [50.0, 200.0, 30.0, 100.0],
        "is_returned": [0, 0, 0, 1],
    })


@pytest.fixture
def monthly_agg():
    return pd.DataFrame({
        "customer_id": [2, 2, 2],
        "txn_month": pd.to_datetime(["2026-05-01", "2026-06-01", "2026-07-01"]),
        "txn_count": [2, 1, 1],
        "total_amount": [150.0, 30.0, 250.0],
        "return_count": [1, 0, 0],
    })


AS_OF = "2026-08-01"


class TestTenureDays:
    def test_normal_case(self, customers):
        result = transforms.tenure_days(customers, AS_OF)
        # customer 1: 2024-01-15 to 2026-08-01 = ~929 days
        # customer 2: 2025-06-01 to 2026-08-01 = ~426 days
        # customer 3: 2025-01-01 to 2026-08-01 = ~577 days
        assert len(result) == 3
        assert result.iloc[0] > 900
        assert result.iloc[1] > 400
        assert result.iloc[2] > 500

    def test_zero_activity_case(self, customers):
        # customer 1 has no transactions — tenure is independent of transactions
        result = transforms.tenure_days(customers, AS_OF)
        assert result.iloc[0] > 0  # always positive for a signed-up customer

    def test_single_record_case(self):
        single = pd.DataFrame({
            "customer_id": [42],
            "signup_date": pd.to_datetime(["2026-01-01"]),
        })
        result = transforms.tenure_days(single, AS_OF)
        assert len(result) == 1
        assert result.iloc[0] == (pd.Timestamp(AS_OF) - pd.Timestamp("2026-01-01")).days


class TestDaysSinceLastTxn:
    def test_normal_case(self, customers, transactions):
        result = transforms.days_since_last_txn(customers, transactions, AS_OF)
        # customer 2: last txn 2026-07-15, so ~17 days
        assert result.iloc[1] <= 20  # near as_of
        assert result.iloc[1] >= 0

    def test_zero_activity_case(self, customers, transactions):
        # customer 1 has no transactions — should default to tenure
        result = transforms.days_since_last_txn(customers, transactions, AS_OF)
        tenure = transforms.tenure_days(customers, AS_OF)
        assert result.iloc[0] == tenure.iloc[0]

    def test_single_record_case(self):
        cust = pd.DataFrame({
            "customer_id": [99],
            "signup_date": pd.to_datetime(["2026-01-01"]),
        })
        txns = pd.DataFrame({
            "customer_id": [99],
            "txn_timestamp": pd.to_datetime(["2026-07-01"]),
            "amount": [25.0],
            "is_returned": [0],
        })
        result = transforms.days_since_last_txn(cust, txns, AS_OF)
        assert result.iloc[0] == (pd.Timestamp(AS_OF) - pd.Timestamp("2026-07-01")).days
        assert result.iloc[0] > 0


class TestTxnCountLookback:
    def test_normal_case(self, customers, transactions):
        result = transforms.txn_count_lookback(customers, transactions, AS_OF, 90)
        # customer 2: 3 non-returned txns in last 90 days (May 5 excluded: is_returned=1)
        assert result.iloc[1] == 3
        assert result.iloc[0] == 0  # customer 1: zero activity

    def test_zero_activity_case(self, customers, transactions):
        result = transforms.txn_count_lookback(customers, transactions, AS_OF, 30)
        # customer 1 has no transactions
        assert result.iloc[0] == 0

    def test_time_window_boundary(self, customers, transactions):
        """Test that a transaction exactly at the window boundary is included."""
        # customer 2 has a txn on 2026-06-01 — 61 days before 2026-08-01
        result = transforms.txn_count_lookback(customers, transactions, AS_OF, 61)
        assert result.iloc[1] >= 2  # includes the June txn (61 days back)

    def test_returned_txns_excluded(self, customers, transactions):
        """Verify is_returned=1 rows are not counted."""
        # customer 2: 1 returned txn (2026-05-01, $100) should not appear
        result = transforms.txn_count_lookback(customers, transactions, AS_OF, 365)
        # 3 non-returned txns total for customer 2
        assert result.iloc[1] == 3


class TestGrossSpendLookback:
    def test_normal_case(self, customers, transactions):
        result = transforms.gross_spend_lookback(customers, transactions, AS_OF, 90)
        # customer 2: 50 + 200 + 30 = 280 (excludes the $100 return)
        assert result.iloc[1] == pytest.approx(280.0)

    def test_zero_activity_case(self, customers, transactions):
        result = transforms.gross_spend_lookback(customers, transactions, AS_OF, 30)
        assert result.iloc[0] == 0.0  # customer 1: zero activity
        assert result.iloc[1] == 200.0  # customer 2: 200 (July 15) in last 30 days from Aug 1; July 1 is outside

    def test_returns_excluded(self, customers, transactions):
        """Verify return amounts are not summed into gross spend."""
        result = transforms.gross_spend_lookback(customers, transactions, AS_OF, 365)
        # total non-returned: 50 + 200 + 30 = 280 (not 380 which would include the $100 return)
        assert result.iloc[1] == pytest.approx(280.0)
        assert result.iloc[1] != pytest.approx(380.0)


class TestAvgTxnValueLookback:
    def test_normal_case(self, customers, transactions):
        result = transforms.avg_txn_value_lookback(customers, transactions, AS_OF, 90)
        # customer 2: 280.0 / 3 = 93.33
        assert result.iloc[1] == pytest.approx(280.0 / 3, rel=1e-2)

    def test_zero_activity_case(self, customers, transactions):
        result = transforms.avg_txn_value_lookback(customers, transactions, AS_OF, 30)
        # customer 2: 200.0 / 1 = 200.0 (July 15 only; July 1 is outside 30d window)
        assert result.iloc[1] == pytest.approx(200.0)
        # customer 1: zero activity -> 0.0 (zero-division guard)
        assert result.iloc[0] == 0.0

    def test_zero_purchase_window(self):
        """Customer with txns but none in window should get 0.0, not division-by-zero."""
        cust = pd.DataFrame({
            "customer_id": [50],
            "signup_date": pd.to_datetime(["2025-01-01"]),
        })
        txns = pd.DataFrame({
            "customer_id": [50],
            "txn_timestamp": pd.to_datetime(["2026-01-01"]),
            "amount": [100.0],
            "is_returned": [0],
        })
        # Lookback of 30 days from 2026-08-01 — the Jan txn is outside
        result = transforms.avg_txn_value_lookback(cust, txns, AS_OF, 30)
        assert result.iloc[0] == 0.0


class TestReturnCountLookback:
    def test_normal_case(self, customers, transactions):
        result = transforms.return_count_lookback(customers, transactions, AS_OF, 365)
        # customer 2: 1 return in the May txn
        assert result.iloc[1] == 1

    def test_zero_activity_case(self, customers, transactions):
        result = transforms.return_count_lookback(customers, transactions, AS_OF, 30)
        assert result.iloc[0] == 0  # customer 1: zero activity


class TestActiveMonths12m:
    def test_normal_case(self, customers, monthly_agg):
        result = transforms.active_months_12m(customers, monthly_agg, AS_OF)
        # customer 2: 3 distinct months (May, June, July 2026)
        assert result.iloc[1] == 3

    def test_zero_activity_case(self, customers, monthly_agg):
        # Run ALL tests from the test file
        result = transforms.active_months_12m(customers, monthly_agg, AS_OF)
        assert result.iloc[0] == 0  # customer 1: no parquet rows

    def test_window_boundary(self, customers, monthly_agg):
        """Month exactly at window boundary should be included."""
        result = transforms.active_months_12m(customers, monthly_agg, AS_OF)
        assert result.iloc[1] == 3  # all 3 months within 365 days of 2026-08-01