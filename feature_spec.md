# Feature Specification — E-Commerce Customer Churn Pipeline

## 1. Revision Audit Log (Stage 0 Review Findings & Corrections)

This specification corrects and formalizes the Stage 0 proposal based on manual raw data inspection and spot-check evidence.

| Target Feature / Area | Stage 0 Proposal Defect | Raw Data Reality / Spot-Check Evidence | Required Spec Correction | Business / Technical Justification |
| :--- | :--- | :--- | :--- | :--- |
| **Monetary Aggregations** | Summed `amount` directly without handling returns. | Spot-check revealed `is_returned = 1` rows store positive amounts ($3.00–$439.76). | Apply `WHERE is_returned = 0` filtering to gross spend and purchase count calculations. | Simple `SUM(amount)` inflates gross customer revenue by counting returned merchandise as spend. |
| **Multi-Source Selection** | Undecided trade-off between Parquet and SQLite. | Customer 2 DB spend ($1,068.32, 20 txns) vs Parquet ($934.70, 19 txns). 14.2% of users show cut-off drift. | Mandatory sourcing from `transactions.db` for all rolling lookback features. | Parquet monthly aggregates miss intra-month transaction cutoffs and rolling lookback windows. |
| **Parquet Schema Mapping** | Column hallucination (`month`, `n_transactions`, `pq_calls`). | Inspecting Parquet schema confirmed `txn_month`, `txn_count`, and `pq_cnt`. | Update schema references across dictionary and feature mappings. | Eliminates key/attribute errors during ingestion and transformations. |
| **Zero-Activity Cohort** | Risk of silent `NaN` propagation on missing customer IDs. | 81 customers (e.g., `customer_id` 1, 58, 100) exist in CSV but have 0 transactions in DB. | Mandatory `LEFT JOIN` on `customers.csv` with explicit `COALESCE(..., default)` for every feature. | Prevents silent record dropping and ensures full feature matrix parity for all 1,500 customers. |

---

## 2. Parity Architecture & Guardrails

To eliminate training/scoring feature drift, the pipeline enforces the following structural rules:

* **Single Code Path**: Training matrix generation and single-customer scoring execute through the exact same transformation logic in `features/transforms.py`.
* **As-Of Date Threading**: All temporal calculations strictly enforce `txn_timestamp <= as_of`. No future records are evaluated, eliminating temporal data leakage.
* **Label Isolation**: Churn targets (`customers.csv` -> `churned`) are completely isolated from feature construction modules and only appended during training set generation.

---

## 3. Confirmed Feature Matrix with Churn Rationales

| Feature Name | Primary Source | Exact Computation Logic | Zero-Activity Default | Specific Behavioral Churn Rationale | Anti-Leakage / Guardrail Rule |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tenure_days` | `customers.csv` | `(as_of - signup_date).days` | N/A (1,500 present) | Captures account longevity. Newer accounts have unformed habits and exhibit high early-lifecycle churn, whereas long-tenured accounts churn due to satisfaction decay. | Bounded at $\ge 0$. |
| `days_since_last_txn` | `transactions.db` | `(as_of - max(txn_timestamp)).days` where `txn_timestamp <= as_of` | `tenure_days` | Primary signal of silent attrition. Increasing elapsed time between orders signals that the customer has switched to a competitor or abandoned the platform. | Defaults to customer tenure if no prior transactions exist. |
| `txn_count_lookback` | `transactions.db` | `COUNT(txn_id)` where `txn_timestamp` between `(as_of - window)` and `as_of` | `0` | Order frequency drop-off precedes total abandonment. Decreasing purchase velocity isolates declining share-of-wallet before churn occurs. | Strictly bounded by lookback window duration. |
| `gross_spend_lookback` | `transactions.db` | `SUM(amount)` where `is_returned = 0` and `txn_timestamp` within window | `0.0` | Monetary value contraction (spend decay) measures shrinking basket sizes, distinguishing active high-value spenders from disengaging users. | Filters out return values; defaults to `$0.00`. |
| `avg_txn_value_lookback` | `transactions.db` | `gross_spend_lookback / purchase_count` where `is_returned = 0` | `0.0` | Measures order intensity per valid purchase. Declining Average Order Value (AOV) highlights downgrading behavior (buying cheaper alternatives), distinct from frequency loss. | Denominator counts non-returned purchases only (`is_returned = 0`); zero-division guard applied. |
| `return_count_lookback` | `transactions.db` | `COUNT(txn_id)` where `is_returned = 1` and `txn_timestamp` within window | `0` | Proxy for customer dissatisfaction and post-purchase friction. Frequent returns correlate directly with product sizing/quality disappointment, driving defection. | Evaluates return frequency as an isolated friction signal. |
| `active_months_12m` | `transactions_monthly_agg.parquet` | `COUNT(DISTINCT txn_month)` where `txn_month` within last 365 days of `as_of` | `0` | Captures macro seasonal consistency over yearly cycles. Lapses in active calendar months expose broken recurring purchasing habits. | Read natively from Parquet for calendar-aligned long-horizon activity. |

---

## 4. Multi-Source Decision Matrix

* **`transactions.db` (SQLite)**: Selected as authoritative source for all short/medium rolling windows (`30d`, `60d`, `90d`) and point-in-time recency calculations due to microsecond timestamp precision.
* **`transactions_monthly_agg.parquet`**: Selected solely for macro-level seasonal engagement (`active_months_12m`) where calendar-month alignment minimizes computation overhead without introducing intra-month windowing errors.
* **`customers.csv`**: Sole source of truth for customer entity spine, profile attributes (`region`, `acquisition_channel`), and signup baselines.

---

## 5. Feature Versioning Exercise Specification

To validate local feature store version management, the pipeline implements two distinct versioned features parameterized by lookback windows:

### Versioned Feature 1: `gross_spend_lookback`
* **Parameter**: `lookback_days`
* **Version 1 (`v1.0.0`)**: `lookback_days = 30` (`gross_spend_30d` — captures immediate short-term monetary velocity).
* **Version 2 (`v2.0.0`)**: `lookback_days = 60` (`gross_spend_60d` — captures medium-term spend baseline).
* **Expected Behavioral Difference**: `v2.0.0` monotonically increases or equals `v1.0.0` spend totals. Divergence identifies customers whose spending slowed in the most recent 30 days.

### Versioned Feature 2: `txn_count_lookback`
* **Parameter**: `window_days`
* **Version 1 (`v1.0.0`)**: `window_days = 30` (`txn_count_30d` — short-term purchase frequency).
* **Version 2 (`v2.0.0`)**: `window_days = 90` (`txn_count_90d` — quarterly purchase cadence).
* **Expected Behavioral Difference**: `v2.0.0` captures broader engagement intensity; ratio `v1.0.0 / (v2.0.0 / 3)` exposes velocity deceleration.

---

## 6. Data Quality Checks & Trigger Actions

| Check Name | Target Column / Table | Validation Condition | Trigger Action on Violation |
| :--- | :--- | :--- | :--- |
| `check_null_features` | Engineered Output Matrix | Zero `NULL` or `NaN` values across any feature column. | **Raise Exception** (fails pipeline build immediately). |
| `check_positive_spend` | `gross_spend_lookback` | All spend values $\ge 0.0$. | **Raise Exception** (indicates unfiltered return leakage). |
| `check_customer_spine` | Engine Output | Output row count must exactly equal 1,500 (matching `customers.csv`). | **Raise Exception** (indicates inner join row loss). |
| `check_recency_bounds` | `days_since_last_txn` | Recency must be $\ge 0$ and $\le tenure\_days$. | **Raise Exception** (indicates future transaction leakage or timestamp corruption). |