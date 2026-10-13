"""
Local feature store API: a SQLite metadata/version registry (`feature_store/registry.db`,
table `feature_registry`) plus one parquet value snapshot per registered version
(`feature_store/values/<feature_name>__v<version>.parquet`).

SQLite + parquet only. See skill.md's Workflow section for the exact registry schema.
Never hardcode a parquet filename outside this module — all reads resolve via the registry.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Production defaults.  Tests can monkey-patch `store.REGISTRY_DB` and
# `store.VALUES_DIR` at module level before calling any store function.
REGISTRY_DB = "feature_store/registry.db"
VALUES_DIR = "feature_store/values"


def _get_connection() -> sqlite3.Connection:
    """Get a connection to the registry database, creating tables if needed."""
    Path(REGISTRY_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_registry (
            feature_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            description TEXT NOT NULL,
            source_columns TEXT NOT NULL,
            transform_summary TEXT NOT NULL,
            business_rationale TEXT NOT NULL,
            parameters TEXT NOT NULL,
            parquet_path TEXT NOT NULL,
            is_latest INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (feature_name, version)
        )
    """)
    conn.commit()
    return conn


def register_version(
    feature_name: str,
    values_df: pd.DataFrame,
    description: str,
    source_columns: str,
    transform_summary: str,
    business_rationale: str,
    parameters: dict,
) -> int:
    """Write a new parquet snapshot, insert the registry row, flip is_latest, return the
    new version number.
    """
    conn = _get_connection()
    try:
        # Determine next version number
        cursor = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM feature_registry WHERE feature_name = ?",
            (feature_name,),
        )
        next_version = cursor.fetchone()[0] + 1

        # Build parquet path
        Path(VALUES_DIR).mkdir(parents=True, exist_ok=True)
        parquet_filename = f"{feature_name}__v{next_version}.parquet"
        parquet_path = str(Path(VALUES_DIR) / parquet_filename)

        # Write parquet snapshot (never overwrite an existing file)
        if Path(parquet_path).exists():
            raise FileExistsError(
                f"Parquet file already exists: {parquet_path}. "
                f"Would overwrite version {next_version}."
            )

        # Ensure required columns exist in values_df
        required_cols = {"customer_id", feature_name, "as_of_date"}
        missing = required_cols - set(values_df.columns)
        if missing:
            raise ValueError(
                f"values_df must contain columns: {required_cols}. Missing: {missing}"
            )

        values_df.to_parquet(parquet_path, index=False)

        # Insert registry row and flip is_latest in the same transaction
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("BEGIN")
        # Flip prior latest to 0
        conn.execute(
            "UPDATE feature_registry SET is_latest = 0 WHERE feature_name = ? AND is_latest = 1",
            (feature_name,),
        )
        # Insert new row with is_latest = 1
        conn.execute(
            """
            INSERT INTO feature_registry
                (feature_name, version, created_at, description, source_columns,
                 transform_summary, business_rationale, parameters, parquet_path, is_latest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                feature_name,
                next_version,
                now,
                description,
                source_columns,
                transform_summary,
                business_rationale,
                json.dumps(parameters),
                parquet_path,
            ),
        )
        conn.commit()

        return next_version
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest(feature_name: str) -> pd.DataFrame:
    """Return the DataFrame for the version currently flagged is_latest = 1."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT parquet_path FROM feature_registry "
            "WHERE feature_name = ? AND is_latest = 1",
            (feature_name,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(
                f"No latest version found for feature '{feature_name}'. "
                f"Has it been registered?"
            )
        return pd.read_parquet(row[0])
    finally:
        conn.close()


def get_version(feature_name: str, version: int) -> pd.DataFrame:
    """Return the DataFrame for a specific (feature_name, version)."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT parquet_path FROM feature_registry "
            "WHERE feature_name = ? AND version = ?",
            (feature_name, version),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(
                f"Version {version} of feature '{feature_name}' not found in registry."
            )
        return pd.read_parquet(row[0])
    finally:
        conn.close()


def list_versions(feature_name: str) -> pd.DataFrame:
    """Return every registered version's metadata row for feature_name, most recent first."""
    conn = _get_connection()
    try:
        df = pd.read_sql(
            "SELECT * FROM feature_registry WHERE feature_name = ? ORDER BY version DESC",
            conn,
            params=(feature_name,),
        )
        return df
    finally:
        conn.close()