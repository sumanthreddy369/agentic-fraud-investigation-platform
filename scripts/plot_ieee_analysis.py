"""Render aggregate comparison, reliability and correlation figures; no row-level data."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def main():
    source = Path("artifacts/ieee_cis/full-analysis-v1")
    result = json.loads((source / "analysis.json").read_text())
    output = Path("docs/images")
    output.mkdir(exist_ok=True)
    names = ["logistic", "random_forest", "hist_gradient_boosting"]
    labels = ["Logistic regression", "Random forest", "Histogram boosting"]
    colors = ["#31688e", "#35b779", "#6c4797"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    values = [result["holdout"][name]["raw"]["average_precision"] for name in names]
    bars = axes[0].bar(labels, values, color=colors)
    axes[0].bar_label(bars, fmt="%.3f", padding=4)
    axes[0].set(ylim=(0, 0.5), ylabel="Average precision", title="Retrospective audit: ranking")
    axes[0].tick_params(axis="x", labelrotation=15)
    for name, label, color in zip(names, labels, colors, strict=True):
        bins = result["reliability"][name]["sigmoid"]
        axes[1].plot(
            [b["mean_prediction"] for b in bins],
            [b["observed"] for b in bins],
            "o-",
            label=label,
            color=color,
        )
    axes[1].plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    axes[1].set(
        xlabel="Mean predicted probability",
        ylabel="Observed fraud fraction",
        title="Sigmoid calibration: 10 probability bins",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    axes[1].legend(fontsize=8)
    fig.suptitle("IEEE-CIS | 118,108 audit transactions | Same 15 features", fontsize=14)
    fig.savefig(output / "ieee-comparison-calibration.png", dpi=160)
    plt.close(fig)

    corr = pd.read_csv(source / "serving_feature_correlations.csv", index_col=0)
    fig, ax = plt.subplots(figsize=(9, 8), layout="constrained")
    heat = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90)
    ax.set_yticks(range(len(corr)), corr.index)
    ax.set_title("Serving-feature Pearson correlations | All 590,540 training-source rows")
    fig.colorbar(heat, ax=ax, shrink=0.75, label="Pearson r (pairwise complete)")
    fig.savefig(output / "ieee-serving-correlations.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
