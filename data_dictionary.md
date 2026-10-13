# Data Dictionary — E-Commerce Customer Churn Dataset

## Overview & Multi-Source Architecture

The dataset comprises three heterogeneous data sources located in `data/`. The primary customer spine is defined by `customers.csv`. All pipeline operations enforce left joins originating from this primary key entity to preserve complete coverage across zero-activity cohorts.

---

## Source 1: `data/customers.csv`

* **Format**: CSV
* **Entity Grain**: Customer (1 row per customer)
* **Primary Key**: `customer_id`

| Column Name | Data Type | Nullable | Description / Observed Range | Quality Rules & Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `INTEGER` | No | Monotonically increasing unique ID (1 to 1,500). | Primary Key. 1,500 total rows. No gaps or duplicates. |
| `signup_date` | `DATE` | No | Date of customer registration (`YYYY-MM-DD`). Range: `2024-02-14` to `2026-07-01`. | Validated: All transaction dates occur on or after `signup_date`. |
| `acquisition_channel` | `TEXT` | No | Channel category: `organic` (609), `paid_search` (431), `referral` (295), `social` (165). | Static categorical. Categorical encoding required. |
| `region` | `TEXT` | No | Geographic region: `east` (385), `north` (381), `west` (380), `south` (354). | Static categorical. Balanced across 4 regions. |
| `churned` | `INTEGER` | No | Binary label: `1` = churned (202 / 13.47%), `0` = active (1,298). | **Target Label**: Excluded from feature transforms to prevent leakage. |

---

## Source 2: `data/transactions.db` (SQLite)

* **Format**: SQLite v3 (`transactions` table)
* **Entity Grain**: Individual transaction row (11,742 total rows)
* **Foreign Key**: `customer_id` $\rightarrow$ `customers.csv(customer_id)`

| Column Name | Data Type | Nullable | Description / Observed Range | Quality Rules & Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `INTEGER` | No (in practice) | Foreign Key matching `customers.customer_id`. | **Missing Cohort**: 81 customers have 0 transactions in DB. Must be left-joined. |
| `txn_timestamp` | `TEXT` | No | ISO-8601 timestamp string (`YYYY-MM-DD HH:MM:SS.ssssss`). | Parsed via `pd.to_datetime()`. Timestamp precision used for window filtering. |
| `category` | `TEXT` | No | Product category (`home`, `grocery`, `sports`, `beauty`, `apparel`, `electronics`). | ~1,900–2,000 txns per category. |
| `channel` | `TEXT` | No | Order channel (`web`: 5,278, `mobile_app`: 4,146, `store`: 2,318). | Categorical transaction channel. |
| `amount` | `REAL` | No | Transaction dollar amount ($3.00 to $1,684.21). Mean: $49.72. | **Right-Skewed**: Positive numeric values for both purchases and returns. |
| `is_returned` | `INTEGER` | No | Binary return indicator: `0` = purchase (11,151), `1` = return (591). | **Critical Flag**: Returned rows carry positive `amount`. Must filter `WHERE is_returned = 0`. |

---

## Source 3: `data/transactions_monthly_agg.parquet`

* **Format**: Apache Parquet (8,086 rows)
* **Entity Grain**: Customer x Calendar Month
* **Primary Key**: `(customer_id, txn_month)`

| Column Name | Data Type | Nullable | Description / Observed Range | Quality Rules & Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `INTEGER` | No | Foreign Key matching `customers.customer_id`. | Covers 1,409 customers (91 missing relative to CSV). |
| `txn_month` | `DATETIME` | No | Calendar month start date (`YYYY-MM-01`). | Monthly grain timestamp. |
| `txn_count` | `INTEGER` | No | Monthly purchase count (1 to 32). | Aggregated transaction count. |
| `total_amount` | `FLOAT` | No | Sum of transaction amounts for customer-month. | Subject to as-of cutoff timing discrepancies vs DB. |
| `return_count` | `INTEGER` | No | Monthly return count (0 to 3). | Aggregated return count. |

---

## Known Source Discrepancies & Edge Cases

1. **Cross-Source Cutoff Shift**: Verified on Customer 2 (`transactions.db` = 20 txns / $1,068.32 vs Parquet = 19 txns / $934.70). DB is selected for all rolling window calculations.
2. **Zero-Activity Cohort**: Customer IDs `1`, `58`, `100`, `104`, `117` (and 76 others) have no records in SQLite or Parquet. All transforms apply explicit defaults (`0` count, `$0.00` spend).
3. **Return Values**: `is_returned = 1` rows store positive floating-point amounts. Monetary features explicitly exclude return rows (`WHERE is_returned = 0`).