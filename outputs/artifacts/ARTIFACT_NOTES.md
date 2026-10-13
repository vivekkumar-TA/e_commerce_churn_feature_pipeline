# Artifact Notes — Self-Critique Log

## Things Got Wrong or Reconsidered

### 1. Index Alignment in Transform Functions (Build Debug)

**What happened:** Initial transform functions returned Series indexed by `customer_id` values
(e.g. `1, 2, 3...`), but `build.py` assigned them to a DataFrame with a 0-based integer
index. Pandas aligns on index during assignment, so customer_id=1 (series index value `1`)
mapped to result row index `1`, not row `0` — producing NaN on row 0 for zero-activity
customers.

**Fix:** Changed transforms to always return Series with `customer_id`-based index, and
`build.py` to build features via `pd.concat(feature_dict, axis=1)` which aligns correctly on
the shared customer_id index, then reset_index to get a clean 0-based frame.

**Lesson:** When returning Series from lookup/transform functions, either use `.values` for
positional assignment or ensure the caller aligns by index. The `pd.concat` pattern is more
robust than `result["col"] = series` when indices don't match.

### 2. Windows Console Encoding

**What happened:** Print statements with unicode characters (`✓`, `✗`, `→`) caused
`UnicodeEncodeError` on Windows cp1252 console. File writes had the same issue when using
default encoding.

**Fix:** Replaced unicode glyphs with ASCII alternatives (`[OK]`, `[FAIL]`, `->`) in print
statements. File writes use explicit `encoding="utf-8"` via `io.open()`.

### 3. Zero-Activity Edge Case in `days_since_last_txn`

**What happened:** The initial implementation of `tenure_days` returned a Series with a
default integer index, but `days_since_last_txn` reindexed to customer_id values. The
`result == 0` mask identified zero-activity customers correctly, but alignment failed between
the reindexed result and the tenure series (which had a different index).

**Fix:** When all customers have zero transactions (empty groupby), the function now returns
tenure directly. The helper `_reindex_to_customers` ensures consistent customer_id-based
indexing across all functions.

### 4. Build Script Reloads Raw Data for Versioned Features

**Noted:** The `build_training_features.py` script calls `ingest.load_customers()` and
`ingest.load_transactions()` a second time when registering versioned feature v2 values. This
is slightly redundant with the same calls inside `build_features()`. An optimization would be
to return the loaded data from `build_features()`, but that would change the function's
contract. The current approach is correct (no feature logic duplication) at the cost of an
extra I/O pass on a small dataset.

## Verifications That Passed Cleanly

- **Zero-activity defaults**: Customer 1 correctly shows tenure for recency, 0 for counts,
  0.0 for spend, 0 for active_months_12m across both training and scoring paths.
- **As-of-date threading**: All transforms receive `as_of` as a parameter. Verified by
  comparing build output for different as-of dates.
- **get_latest behavior**: After registering v1 and v2 of both versioned features,
  `get_latest()` correctly returns v2 values.
- **Return exclusion**: Spot-checked `transactions.db` — all 591 return rows have
  `is_returned = 1` and are correctly excluded from gross spend and purchase count features.
- **Cross-source disagreement acknowledged**: The multi-source decision (DB for rolling
  windows, Parquet for active_months_12m) is documented but the pipeline does not attempt to
  reconcile the $133.62/1-txn discrepancy on Customer 2 — that is a data-source fact, not a
  pipeline bug.

---

*Generated as part of the churn feature pipeline build step.*