# Feature Lineage

> Auto-generated from `features/schema.py` and `feature_store/store.py`. Every feature,
> across every stored version, documents its source(s), transform, rationale, and
> feature-store location.

---

## tenure_days

| Property | Value |
|---|---|
| **Source** | `customers.csv` |
| **Transform** | `(as_of - signup_date).days` |
| **Business Rationale** | Captures account longevity. Newer accounts have unformed habits and exhibit high early-lifecycle churn, whereas long-tenured accounts churn due to satisfaction decay. |
| **Nullable** | No (always present for all 1,500 customers) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{}` | `feature_store/values/tenure_days__v1.parquet` |

---

## days_since_last_txn

| Property | Value |
|---|---|
| **Source** | `transactions.db` (`transactions.txn_timestamp`) |
| **Transform** | `(as_of - max(txn_timestamp)).days` where `txn_timestamp <= as_of`; zero-activity customers default to `tenure_days` |
| **Business Rationale** | Primary signal of silent attrition. Increasing elapsed time between orders signals that the customer has switched to a competitor or abandoned the platform. |
| **Nullable** | No (tenure default ensures non-null for all customers) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{}` | `feature_store/values/days_since_last_txn__v1.parquet` |

---

## txn_count_lookback

| Property | Value |
|---|---|
| **Source** | `transactions.db` (`transactions.txn_timestamp`) |
| **Transform** | `COUNT(txn_id)` where `is_returned = 0` and `txn_timestamp` within lookback window before `as_of`. |
| **Business Rationale** | Order frequency drop-off precedes total abandonment. Decreasing purchase velocity isolates declining share-of-wallet before churn occurs. |
| **Nullable** | No (0 default for zero-activity customers) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{"window_days": 30}` | `feature_store/values/txn_count_lookback__v1.parquet` |
| v2.0.0 | `{"window_days": 90}` | `feature_store/values/txn_count_lookback__v2.parquet` |

---

## gross_spend_lookback

| Property | Value |
|---|---|
| **Source** | `transactions.db` (`transactions.amount`, `transactions.txn_timestamp`) |
| **Transform** | `SUM(amount)` where `is_returned = 0` and `txn_timestamp` within lookback window before `as_of`. |
| **Business Rationale** | Monetary value contraction (spend decay) measures shrinking basket sizes, distinguishing active high-value spenders from disengaging users. |
| **Nullable** | No (0.0 default for zero-activity customers) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{"lookback_days": 30}` | `feature_store/values/gross_spend_lookback__v1.parquet` |
| v2.0.0 | `{"lookback_days": 60}` | `feature_store/values/gross_spend_lookback__v2.parquet` |

---

## avg_txn_value_lookback

| Property | Value |
|---|---|
| **Source** | `transactions.db` (derived from `gross_spend_lookback` / `txn_count_lookback`) |
| **Transform** | `gross_spend_lookback / txn_count_lookback` (both from non-returned purchases only); zero-division guard returns 0.0 |
| **Business Rationale** | Measures order intensity per valid purchase. Declining AOV highlights downgrading behavior (buying cheaper alternatives), distinct from frequency loss. |
| **Nullable** | No (0.0 default for zero-activity and zero-purchase windows) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{}` | `feature_store/values/avg_txn_value_lookback__v1.parquet` |

---

## return_count_lookback

| Property | Value |
|---|---|
| **Source** | `transactions.db` (`transactions.txn_timestamp`, `transactions.is_returned`) |
| **Transform** | `COUNT(txn_id)` where `is_returned = 1` and `txn_timestamp` within lookback window before `as_of`. |
| **Business Rationale** | Proxy for customer dissatisfaction and post-purchase friction. Frequent returns correlate directly with product sizing/quality disappointment, driving defection. |
| **Nullable** | No (0 default for zero-activity customers) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{}` | `feature_store/values/return_count_lookback__v1.parquet` |

---

## active_months_12m

| Property | Value |
|---|---|
| **Source** | `transactions_monthly_agg.parquet` (`txn_month`) |
| **Transform** | `COUNT(DISTINCT txn_month)` where `txn_month` within last 365 days of `as_of`. |
| **Business Rationale** | Captures macro seasonal consistency over yearly cycles. Lapses in active calendar months expose broken recurring purchasing habits. |
| **Nullable** | No (0 default for customers missing from parquet) |

### Stored Versions

| Version | Parameters | Parquet Path |
|---|---|---|
| v1.0.0 | `{}` | `feature_store/values/active_months_12m__v1.parquet` |

---

*Generated from `features/schema.py` and `feature_store/registry.db`.*