#!/usr/bin/env python3
"""
Version comparison for the two versioned features designated in feature_spec.md:
  - gross_spend_lookback (v1: 30d, v2: 60d)
  - txn_count_lookback (v1: 30d, v2: 90d)

Loads all registered versions via the feature store, compares distributions, and
writes results to VERSION_COMPARISON.md.
"""

from feature_store.store import get_version, list_versions


def compare_feature_versions(feature_name: str) -> dict:
    """Load all versions of a feature and compute comparison stats."""
    versions_df = list_versions(feature_name)
    if versions_df.empty:
        return {"feature": feature_name, "versions": [], "error": "No versions found"}

    version_numbers = sorted(versions_df["version"].tolist())
    versions_data = {}
    for v in version_numbers:
        df = get_version(feature_name, v)
        values = df[feature_name]
        versions_data[v] = {
            "count": len(values),
            "sum": float(values.sum()),
            "mean": float(values.mean()),
            "std": float(values.std()),
            "min": float(values.min()),
            "p25": float(values.quantile(0.25)),
            "median": float(values.median()),
            "p75": float(values.quantile(0.75)),
            "max": float(values.max()),
            "nonzero_rate": float((values > 0).mean()),
        }

    # Compare adjacent versions
    comparisons = []
    for i in range(len(version_numbers) - 1):
        v_early = version_numbers[i]
        v_late = version_numbers[i + 1]
        early_df = get_version(feature_name, v_early)
        late_df = get_version(feature_name, v_late)

        # Align on customer_id
        merged = early_df[["customer_id", feature_name]].merge(
            late_df[["customer_id", feature_name]],
            on="customer_id",
            suffixes=(f"_v{v_early}", f"_v{v_late}"),
        )

        changed_count = (merged[f"{feature_name}_v{v_early}"] != merged[f"{feature_name}_v{v_late}"]).sum()
        avg_abs_change = float((merged[f"{feature_name}_v{v_late}"] - merged[f"{feature_name}_v{v_early}"]).abs().mean())
        mean_delta = float((merged[f"{feature_name}_v{v_late}"] - merged[f"{feature_name}_v{v_early}"]).mean())

        # Rank-order change (Spearman-like: how many customers move position)
        merged["rank_v_early"] = merged[f"{feature_name}_v{v_early}"].rank(method="average")
        merged["rank_v_late"] = merged[f"{feature_name}_v{v_late}"].rank(method="average")
        rank_shift = float((merged["rank_v_early"] - merged["rank_v_late"]).abs().mean())

        comparisons.append({
            "from_version": v_early,
            "to_version": v_late,
            "changed_count": int(changed_count),
            "changed_pct": round(changed_count / len(merged) * 100, 2),
            "avg_abs_change": avg_abs_change,
            "mean_delta": mean_delta,
            "avg_rank_shift": rank_shift,
        })

    return {
        "feature": feature_name,
        "versions": versions_data,
        "comparisons": comparisons,
    }


def write_version_comparison(results: list[dict]) -> str:
    """Generate the VERSION_COMPARISON.md content."""
    lines = [
        "# Version Comparison Report",
        "",
        "## Overview",
        "",
        f"This report compares every registered version of the two features designated for "
        f"versioning in `feature_spec.md` Section 5: `gross_spend_lookback` (30d vs 60d "
        f"window) and `txn_count_lookback` (30d vs 90d window).",
        "",
        "All versions were loaded from the feature store via `get_version()`. No features "
        "were recomputed from scratch for this report.",
        "",
        "---",
        "",
    ]

    for result in results:
        feature = result["feature"]
        lines.append(f"## {feature}")
        lines.append("")

        if "error" in result:
            lines.append(f"**Error:** {result['error']}")
            lines.append("")
            continue

        # Version stats table
        lines.append("### Per-Version Descriptive Statistics")
        lines.append("")
        lines.append("| Version | Count | Sum | Mean | Std | Min | P25 | Median | P75 | Max | Non-Zero Rate |")
        lines.append("|---------|-------|-----|------|-----|-----|-----|--------|-----|-----|---------------|")
        for v, stats in sorted(result["versions"].items()):
            lines.append(
                f"| v{v} | {stats['count']} | ${stats['sum']:.2f} | ${stats['mean']:.2f} "
                f"| ${stats['std']:.2f} | ${stats['min']:.2f} | ${stats['p25']:.2f} "
                f"| ${stats['median']:.2f} | ${stats['p75']:.2f} | ${stats['max']:.2f} "
                f"| {stats['nonzero_rate']:.1%} |"
            )
        lines.append("")

        # Version comparison
        lines.append("### Version-to-Version Comparison")
        lines.append("")
        for comp in result["comparisons"]:
            lines.append(f"**v{comp['from_version']} -> v{comp['to_version']}:**")
            lines.append(f"- Customers with changed values: **{comp['changed_count']} ({comp['changed_pct']}%)**")
            lines.append(f"- Mean absolute change: **${comp['avg_abs_change']:.2f}**")
            lines.append(f"- Mean delta (v{comp['to_version']} - v{comp['from_version']}): **${comp['mean_delta']:.2f}**")
            lines.append(f"- Average rank-order shift: **{comp['avg_rank_shift']:.2f} positions**")
            lines.append("")

        # Interpretation
        lines.append("### Interpretation")
        lines.append("")
        if feature == "gross_spend_lookback":
            lines.append(
                "Extending the lookback window from 30 to 60 days monotonically increases "
                "spend totals for any customer with non-zero spend in the 31–60 day range. "
                "The gap between v1 and v2 (mean v2 - v1) identifies customers whose "
                "spending slowed in the most recent 30 days — a velocity deceleration signal. "
                "A model consuming this feature would notice the shift because the "
                "distribution spread (std, P75, max) grows when including the broader window."
            )
        elif feature == "txn_count_lookback":
            lines.append(
                "Extending the window from 30 to 90 days captures a broader quarterly "
                "purchase cadence. Customers with infrequent but consistent purchase "
                "behavior (e.g. once per month) show a higher count in v2 while appearing "
                "low-activity in v1. The ratio v1 / (v2/3) exposes velocity deceleration "
                "when v1 contributes less than one-third of the quarterly total. The "
                "distribution shifts significantly because the 90-day window captures more "
                "transaction events for most customers."
            )
        lines.append("---")
        lines.append("")

    lines.append(
        "*Generated by `scripts/compare_feature_versions.py`. All values loaded from "
        "the feature store.*"
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    versioned_features = ["gross_spend_lookback", "txn_count_lookback"]
    results = []

    for feature in versioned_features:
        print(f"Comparing versions for {feature}...")
        result = compare_feature_versions(feature)
        results.append(result)
        vcount = len(result.get("versions", {}))
        comps = result.get("comparisons", [])
        print(f"  Found {vcount} version(s), {len(comps)} comparison(s)")

    # Write VERSION_COMPARISON.md
    content = write_version_comparison(results)
    # Use utf-8 encoding for unicode characters (arrows, math symbols)
    import io
    with io.open("outputs/artifacts/VERSION_COMPARISON.md", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n[DONE] VERSION_COMPARISON.md written to outputs/artifacts/")


if __name__ == "__main__":
    main()