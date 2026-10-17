import csv
import json
from pathlib import Path

p = Path("artifacts/ieee_cis/full-analysis-v1")
r = json.loads((p / "analysis.json").read_text())
lines = [
    "# Expanded IEEE CIS analysis and model comparison",
    "",
    "Completed October 13, 2026. This is an educational retrospective analysis, "
    "not production validation. Raw outputs and prediction rows remain in "
    "ignored artifacts/ieee_cis/full-analysis-v1.",
    "",
    "## Scope and limitations",
    "",
    "Full-source transaction and identity descriptive statistics, missingness, "
    "cardinalities, category fraud rates, and key checks were computed. All 15 "
    "serving-feature correlations use all 590540 rows. The wider numeric "
    "correlation matrix uses a reproducible 50000-row sample; it is not an "
    "all-row calculation. Unlabeled competition transactions were checked for "
    "duplicate/disjoint IDs and descriptive feature distributions. Identity "
    "test schema normalization and prospective drift tests are future work.",
    "",
    "The final 20% was previously evaluated by baseline v1. It is called an "
    "audit holdout and is not a pristine final test. No protected demographic "
    "attributes were available; subgroup results below describe business "
    "categories only. Groups below 100 rows are omitted.",
    "",
    "## Temporal partitions",
    "",
    "| Partition | Rows | Use |",
    "| --- | ---: | --- |",
]
for name, use in [
    ("train", "Fit all candidate models"),
    ("selection", "Choose highest average precision"),
    ("calibration", "Fit sigmoid calibrators"),
    ("audit_holdout", "Report final retrospective results"),
]:
    lines.append(f"| {name} | {r['partitions'][name]} | {use} |")
lines += [
    "",
    "All models use TransactionAmt and C1 through C14, with fixed -999 blank "
    "encoding. Logistic regression scales inputs using training-only "
    "statistics. No threshold tuning was performed.",
    "",
    "## Model selection period",
    "",
    "| Model | ROC AUC | Average precision | Fit seconds |",
    "| --- | ---: | ---: | ---: |",
]
for name, v in r["selection"].items():
    lines.append(
        f"| {name} | {v['roc_auc']:.4f} | {v['average_precision']:.4f} | {v['fit_seconds']:.1f} |"
    )
lines += [
    "",
    f"Selected by selection-period average precision: **{r['selected_by_selection_ap']}**.",
    "",
    "## Audit comparison before and after calibration",
    "",
    "| Model | Output | ROC AUC | AP | Brier | Log loss | Precision | Recall | FPR |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
]
for name, variants in r["holdout"].items():
    for variant in ["raw", "sigmoid"]:
        if variant not in variants:
            continue
        v = variants[variant]
        prec = "undefined" if v["precision"] is None else f"{v['precision']:.3f}"
        lines.append(
            f"| {name} | {variant} | {v['roc_auc']:.4f} | "
            f"{v['average_precision']:.4f} | {v['brier']:.5f} | {v['log_loss']:.5f} | "
            f"{prec} | {v['recall']:.3f} | {v['false_positive_rate']:.4f} |"
        )
lines += [
    "",
    "Precision, recall, and FPR use threshold 0.5. Smaller Brier/log loss is "
    "better. Calibration does not necessarily improve every model or every "
    "future period. AP is average precision, not trapezoidal PR-AUC.",
    "",
    "## Subgroup analysis of calibrated selection winner",
    "",
    "| Dimension | Group | Rows | Prevalence | AP | Recall | FPR | Brier |",
    "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
]
for dim, groups in r["subgroups"].items():
    for v in groups:

        def fmt(k, values=v):
            return "undefined" if values[k] is None else f"{values[k]:.4f}"

        lines.append(
            f"| {dim} | {v['group']} | {v['rows']} | {fmt('prevalence')} | "
            f"{fmt('average_precision')} | {fmt('recall')} | "
            f"{fmt('false_positive_rate')} | {fmt('brier')} |"
        )
lines += [
    "",
    "These are descriptive differences, not causal findings or fairness "
    "certification. Small positive-class counts make recall unstable even when "
    "a group has more than 100 rows.",
    "",
    "## Calibration reliability tables",
    "",
    "| Model | Output | Bin lower bound | Rows | Mean prediction | Observed fraud rate |",
    "| --- | --- | ---: | ---: | ---: | ---: |",
]
for name, variants in r["reliability"].items():
    for variant, bins in variants.items():
        for b in bins:
            lines.append(
                f"| {name} | {variant} | {b['lower']:.1f} | {b['rows']} | "
                f"{b['mean_prediction']:.4f} | {b['observed']:.4f} |"
            )
lines += [
    "",
    "## Correlation findings",
    "",
    "Pearson correlations use pairwise complete observations; correlations are "
    "associations, not causes. Missingness patterns and anonymized feature "
    "definitions constrain interpretation.",
    "",
    "| Feature pair | Pearson correlation |",
    "| --- | ---: |",
]
with (p / "serving_feature_correlations.csv").open() as f:
    reader = csv.DictReader(f)
    pairs = []
    for row in reader:
        a = row[""]
        for b, value in row.items():
            if b and a < b and value:
                pairs.append((abs(float(value)), a, b, float(value)))
for _, a, b, v in sorted(pairs, reverse=True)[:20]:
    lines.append(f"| {a} and {b} | {v:.4f} |")
lines += [
    "",
    "## Deployment model decision",
    "",
    "Histogram gradient boosting won statistical selection but the installed "
    "skl2onnx converter failed on a boolean tree attribute. Its failure is "
    "preserved in the work record; it was not replaced as the reported winner. "
    "The calibrated random forest is the deployable fallback, version "
    "ieee-rf15-sigmoid-v2. Its ONNX graph includes sigmoid calibration, and "
    "parity was checked on all audit rows. Ten protected FastAPI golden "
    "requests passed. No claim is made that the fallback is the best candidate.",
    "",
    "## Saved reproducible outputs",
    "",
    "scripts/analyze_ieee_full.py creates descriptive tables, quality tables, "
    "correlations, category summaries, reliability/subgroup results and private "
    "predictions. scripts/export_selected_model.py exports the documented "
    "random-forest fallback using the recorded calibration parameters. "
    "Dependency versions are locked in uv.lock. No raw rows or binaries belong "
    "in Git.",
]
lines += [
    "",
    "## Figures",
    "",
    "![Model comparison and calibration](images/ieee-comparison-calibration.png)",
    "",
    "![Full-row serving-feature correlations](images/ieee-serving-correlations.png)",
    "",
    "## Reproduce",
    "",
    "Run from the repository root with the approved IEEE-CIS CSVs in data/raw/ieee_cis.",
    "Output directories must not already exist; archive an earlier run before repeating.",
    "```powershell",
    "uv sync --frozen --extra training --extra onnx-cpu",
    "uv run python scripts/analyze_ieee_full.py --raw data/raw/ieee_cis "
    "--output artifacts/ieee_cis/full-analysis-v1",
    "uv run python scripts/export_selected_model.py",
    "uv run python scripts/verify_model_api.py --model-dir artifacts/ieee_cis/model-v2",
    "uv run python scripts/report_ieee_analysis.py",
    "uv run python scripts/plot_ieee_analysis.py",
    "```",
    "",
    "The export and report helpers use the documented default folders. Raw source, "
    "predictions and model files stay private. The analysis also records the source SHA-256.",
    "The old v1 baseline used a larger training split; its metrics are not a fair "
    "same-split comparison against these three candidates.",
    "",
    "## Remaining model work",
    "",
    "Validate the deployed fallback by subgroup independently; current subgroup tables "
    "describe the statistical winner. Resolve the histogram-model ONNX converter failure, "
    "evaluate a locked prospective period, add uncertainty intervals, select thresholds "
    "using business costs on validation data, and monitor drift before any real use.",
    "Agent investigations, MLflow/Airflow and monitoring remain Target (not built yet).",
]
Path("docs/FULL_EDA_COMPARISON.md").write_text("\n".join(lines) + "\n")
print(json.dumps(r["holdout"]["hist_gradient_boosting"], indent=2))
