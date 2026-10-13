# E-Commerce Churn Feature Engineering Pipeline & Local Feature Store

A production-grade, reproducible feature engineering pipeline and local feature store designed for customer churn prediction. Built with strict point-in-time temporal guarantees (`as_of` threading), guaranteed train/score parity via a single shared code path, multi-source conflict resolution, and deterministic data quality guardrails.

---

## Architecture & Key Design Decisions

1. **Guaranteed Train/Score Parity**: Training feature generation and single-customer real-time scoring share an identical transformation entry point (`features.build:build_features`). Parity is verified via automated assertions and mutation testing.
2. **Strict Point-in-Time Correctness**: All transaction queries and rolling windows enforce `txn_timestamp <= as_of`, eliminating temporal leakage across all training and scoring runs.
3. **Multi-Source Hierarchy**:
   - `data/customers.csv`: Authoritative 1,500-customer spine and static attributes (`signup_date`, `region`, `acquisition_channel`). Target label `churned` is strictly isolated from feature logic.
   - `data/transactions.db`: Authoritative source for all rolling lookback windows (`30d`, `60d`, `90d`) and recency calculations due to microsecond timestamp precision.
   - `data/transactions_monthly_agg.parquet`: Sourced exclusively for macro-calendar engagement (`active_months_12m`), avoiding intra-month aggregation boundary drift.
4. **Return Transaction Filtering**: Filters `WHERE is_returned = 0` on gross spend and purchase volume calculations, preventing positive return amounts ($3.00–$439.76) from artificially inflating customer spend metrics. Returns are tracked independently as a dissatisfaction metric (`return_count_lookback`).
5. **Zero-Activity Cohort Handling**: Implements a `LEFT JOIN` on the customer spine with deterministic default values (`0.0` spend, `0` count, `tenure_days` recency) to prevent silent record dropping or `NaN` values for the 81 inactive customer accounts.
6. **Isolated Test Execution**: Unit tests execute against dynamic pytest `tmp_path` directories, isolating test execution state from production feature store artifacts.

---

## Repository Structure

```
feature-pipelines/
├── data/
│   ├── customers.csv                      # Primary customer spine (1,500 rows)
│   ├── transactions.db                    # Authoritative SQLite transaction log
│   └── transactions_monthly_agg.parquet   # Monthly customer rollups
├── features/
│   ├── ingest.py                          # Pure I/O loaders for CSV, SQLite, and Parquet
│   ├── transforms.py                      # Pure transformation functions with default logic
│   ├── schema.py                          # Schema metadata and non-null constraints
│   ├── quality_checks.py                  # Deterministic pipeline validation rules
│   └── build.py                           # Single shared build_features() code path
├── feature_store/
│   ├── store.py                           # LocalFeatureStore class (SQLite registry + Parquet)
│   ├── registry.db                        # Metadata registry tracking versions and is_latest
│   └── values/                            # Persisted feature snapshot Parquet files
├── scripts/
│   ├── build_training_features.py         # Full dataset batch pipeline & store registration
│   ├── score_customer.py                  # Single-customer point-in-time scoring script
│   └── compare_feature_versions.py        # Statistical comparison between feature versions
├── tests/
│   ├── test_transforms.py                 # Transform tests (boundaries, returns, zero-activity)
│   ├── test_parity.py                     # Batch vs single-customer parity & mutation tests
│   ├── test_quality_checks.py             # Validation check pass/fail behavior tests
│   └── test_feature_store.py              # Registry, retrieval, and versioning tests (tmp_path)
├── skills/
│   └── churn-feature-pipeline/
│       ├── skill.md                       # Pipeline specification standard
│       └── README.md
├── outputs/
│   └── artifacts/
│       ├── FEATURE_LINEAGE.md             # End-to-end data lineage for every feature version
│       ├── VERSION_COMPARISON.md          # Numerical and distribution drift analysis
│       ├── PARITY_CHECK.md                # Verification log for train/score parity
│       ├── ARTIFACT_NOTES.md              # Technical engineering log and bug resolutions
│       └── review_log.md                  # Comprehensive Stage 3 self-review checklist
├── feature_spec.md                        # Formalized feature specifications & churn rationales
├── data_dictionary.md                     # Source schemas, constraints, and observed values
├── README.md                              # Repository overview and execution guide
├── requirements.txt                       # Project dependencies
└── pytest.ini                             # Pytest execution configuration
```

---

## Setup & Installation

### 1. Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install required dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Execution Guide

### 1. Build Training Features & Register Store Snapshots
Computes all 7 candidate features as of `2026-08-01`, validates data quality checks, registers versions in `feature_store/registry.db`, and exports snapshots to `feature_store/values/*.parquet`:

```bash
python -m scripts.build_training_features
```

### 2. Point-in-Time Single-Customer Scoring
Scores individual customer records using the exact same transformation code path:

```bash
python -m scripts.score_customer --customer-id 2 --as-of 2026-08-01
```

### 3. Feature Version Comparison
Computes statistical and distributional differences across registered versions (`gross_spend_lookback` 30d vs 60d, and `txn_count_lookback` 30d vs 90d):

```bash
python -m scripts.compare_feature_versions
```

### 4. Run Test Suite
Executes the test suite (40 unit and integration tests covering transforms, quality checks, feature store operations, and train/score parity):

```bash
pytest -v
```

---

## Feature Store Specification

| Feature Name | Primary Source | Windows / Versions | Default Value | Description |
| :--- | :--- | :--- | :--- | :--- |
| `tenure_days` | `customers.csv` | `v1` | N/A | Account age in days relative to `as_of`. |
| `days_since_last_txn` | `transactions.db` | `v1` | `tenure_days` | Days since the customer's most recent purchase. |
| `txn_count_lookback` | `transactions.db` | `v1` (30d), `v2` (90d) | `0` | Count of non-returned transactions within lookback window. |
| `gross_spend_lookback` | `transactions.db` | `v1` (30d), `v2` (60d) | `0.0` | Sum of transaction amounts (`is_returned = 0`) within window. |
| `avg_txn_value_lookback` | `transactions.db` | `v1` | `0.0` | Average transaction amount per non-returned order. |
| `return_count_lookback` | `transactions.db` | `v1` | `0` | Total return events (`is_returned = 1`) within window. |
| `active_months_12m` | `transactions_monthly_agg.parquet` | `v1` | `0` | Distinct calendar months with recorded purchase activity. |

---

## Data Quality Guardrails

The pipeline executes four deterministic validation checks before saving or registering features. Any validation failure raises an immediate exception and halts execution:

1. **`check_no_unexpected_nulls`**: Asserts zero `NULL` or `NaN` values across all columns after applying default values.
2. **`check_positive_spend`**: Asserts that `gross_spend_lookback` is non-negative (>= 0.0) across all customers.
3. **`check_customer_spine`**: Asserts output row counts match the 1,500 customer spine, verifying no records were dropped during join operations.
4. **`check_recency_bounds`**: Asserts recency is logically bounded (0 <= days_since_last_txn <= tenure_days), catching future leakage and timestamp anomalies.