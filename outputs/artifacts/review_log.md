# Review Log — Step 3 Self-Review

## Review Scope

Full diff of the pipeline build: ingestion, transforms, build module, feature store, quality
checks, lineage doc, and tests. Reviewed as if seeing for the first time, with attention to:

1. Any place training and scoring could silently diverge
2. Any feature whose null/default handling doesn't match what the spec promised
3. Any place the feature store could silently overwrite a version instead of creating a new one
4. Test isolation and side-effect guarantees on persistent feature store artifacts

---

## Finding 1: Training/Scoring Parity — Single Code Path

**Status: RESOLVED** (correct as-is)

`build_features(as_of, source_paths, customer_ids)` is the one shared entry point. The only
difference between training and scoring is the `customer_ids` filter at the top of the
function. All transforms run identically. This was verified by the parity test which asserts
identical feature values for the same customer across both paths.

**No fix needed.** The parity test also passed a mutation check (deliberately splitting the
code path was caught by the test), confirming the test is load-bearing.

---

## Finding 2: Zero-Activity Defaults vs. Spec

**Status: RESOLVED** (correct as-is)

Cross-referenced every feature's default in `feature_spec.md` Section 3 against
`transforms.py`:

| Feature | Spec Default | Actual Default | Match? |
|---|---|---|---|
| `tenure_days` | N/A (always present) | Computed from signup | OK |
| `days_since_last_txn` | `tenure_days` | `tenure_days` for zero-activity | OK |
| `txn_count_lookback` | `0` | `0` | OK |
| `gross_spend_lookback` | `0.0` | `0.0` | OK |
| `avg_txn_value_lookback` | `0.0` | `0.0` | OK |
| `return_count_lookback` | `0` | `0` | OK |
| `active_months_12m` | `0` | `0` | OK |

No mismatches found. All defaults match. Quality check `check_no_unexpected_nulls` confirms
no nulls exist in the output after defaults are applied.

**No fix needed.**

---

## Finding 3: Feature Store Version Overwrite Protection

**Status: RESOLVED** (correct as-is)

`register_version()` in `store.py` checks `if Path(parquet_path).exists()` and raises
`FileExistsError` before overwriting. This prevents silent version overwrites. The atomic
`BEGIN`/`COMMIT`/`ROLLBACK` pattern on the registry ensures that is_latest flips and the new
row insert happen together.

The test suite confirms:
- `test_register_and_retrieve_all_versions_of_a_versioned_feature`: v1 and v2 both retrievable
- `test_is_latest_points_to_highest_version_not_an_earlier_one`: confirmed v2 is returned by
  `get_latest()` after v2 is registered
- `test_list_versions_returns_distinct_parquet_paths_that_exist`: all 3 checks pass

**No fix needed.**

---

## Finding 4: Test Coverage Gaps

**Status: RESOLVED** (all spec'd features covered)

Diffed `feature_spec.md` candidate features against the test suite:

| Feature | Normal | Zero-Activity | Single-Record | Window Boundary | Return Exclusion |
|---|---|---|---|---|---|
| `tenure_days` | ✓ | ✓ | ✓ | N/A | N/A |
| `days_since_last_txn` | ✓ | ✓ | ✓ | N/A | N/A |
| `txn_count_lookback` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `gross_spend_lookback` | ✓ | ✓ | N/A | N/A | ✓ |
| `avg_txn_value_lookback` | ✓ | ✓ | ✓ | N/A | N/A |
| `return_count_lookback` | ✓ | ✓ | N/A | N/A | N/A |
| `active_months_12m` | ✓ | ✓ | N/A | ✓ | N/A |

All features covered. The quality checks test covers every check from the spec (nulls,
positive spend, customer spine count, recency bounds) with both pass and fail variants.

**No fix needed.**

---

## Finding 5: Remaining Minor Concerns

**Status: NO ACTION NEEDED** (by design)

1. **Repeated I/O in build script**: `build_training_features.py` calls `ingest.load_*()` a
   second time for versioned feature v2 registration. This is a performance concern (2x I/O)
   but not a correctness one. Changing `build_features()` to also return loaded data would
   break the clean function contract. Left as-is.

2. **Cross-source timing gap not reconciled**: The $133.62/1-txn discrepancy on Customer 2
   between DB and Parquet is a data-source fact. The pipeline chooses one source per feature
   (DB for rolling windows, Parquet for monthly aggregate) and does not attempt to reconcile
   them. This is the correct design per the multi-source decision in the spec.

3. **No explicit drift check (distribution comparison)**: The `check_drift` stub in the
   starter code's `quality_checks.py` was not implemented because the spec doesn't require a
   distributional drift check. The spec's four concrete checks (nulls, positive spend, row
   count, recency bounds) are all present and raising exceptions.

---

## Finding 6: Test Fixture Isolation & Artifact Preservation

**Status: RESOLVED** (Fixed)

- **Issue Identified**: Running `pytest` executed a cleanup teardown fixture in `tests/test_feature_store.py` that deleted `feature_store/registry.db` and all Parquet snapshot files in `feature_store/values/` upon completion, wiping out production artifacts required for submission.
- **Root Cause**: The test suite initialized database connections and parquet writes directly against the production `feature_store/` workspace path instead of an isolated temporary directory.
- **Action Taken**: Refactored `tests/test_feature_store.py` to utilize `pytest`'s built-in `tmp_path` fixture for all temporary SQLite database instantiation and Parquet file I/O operations.
- **Verification**: Re-ran `python -m scripts.build_training_features` followed by `pytest -v`. All 40 unit tests passed cleanly while maintaining `feature_store/registry.db` and all 9 Parquet snapshots in `feature_store/values/`.

---

## Summary

| Finding | Status | Action Taken |
|---|---|---|
| Training/scoring divergence risk | Clean | Single code path verified by parity test + mutation check |
| Default mismatch with spec | Clean | All 7 features match spec defaults |
| Version overwrite risk | Clean | FileExistsError guard + atomic transactions |
| Test coverage gaps | Clean | 40 tests covering all spec'd features and quality checks |
| Minor concerns | Noted | Performance, cross-source gap, drift check left by design |
| Test fixture artifact deletion risk | Clean (Fixed) | Refactored test fixtures to use `tmp_path`; production store preserved |

*Generated as part of the Step 3 self-review per skill.md.*