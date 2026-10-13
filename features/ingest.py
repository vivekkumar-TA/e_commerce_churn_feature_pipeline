"""
Pure I/O loaders for the three heterogeneous raw sources described in
`data_dictionary.md`. No feature logic belongs here — only loading and basic
type coercion, so ingestion can be unit-tested and swapped independently of
`transforms.py`.
"""

import sqlite3
from pathlib import Path

import pandas as pd


def load_customers(path: str = "data/customers.csv") -> pd.DataFrame:
    """Load customers.csv.

    - Reads the CSV with pandas.
    - Parses `signup_date` as a date.
    - Returns one row per customer_id, unmodified otherwise.
    """
    df = pd.read_csv(path, parse_dates=["signup_date"])
    return df


def load_transactions(path: str = "data/transactions.db") -> pd.DataFrame:
    """Load the row-level `transactions` table from the SQLite database.

    - Connects with sqlite3 (or pandas.read_sql) against `path`.
    - Casts `txn_timestamp` to a real datetime (SQLite stores it as ISO-8601 text).
    - Casts `is_returned` to a clean 0/1 int.
    - Returns the full row-level frame — does not aggregate here.
    """
    with sqlite3.connect(path) as conn:
        df = pd.read_sql("SELECT * FROM transactions", conn)
    df["txn_timestamp"] = pd.to_datetime(df["txn_timestamp"])
    df["is_returned"] = df["is_returned"].astype(int)
    return df


def load_monthly_agg(path: str = "data/transactions_monthly_agg.parquet") -> pd.DataFrame:
    """Load the pre-aggregated customer x month parquet extract.

    - Reads the parquet file with pandas.
    - Parses `txn_month` as a date (first-of-month).
    - Returns as-is — customers/months with zero activity have no row.
    """
    df = pd.read_parquet(path)
    df["txn_month"] = pd.to_datetime(df["txn_month"])
    return df