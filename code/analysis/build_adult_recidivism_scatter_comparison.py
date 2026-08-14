from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
from matplotlib.ticker import PercentFormatter

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "breath_panel_2026_update"
TABLE_PATH = OUT_DIR / "tables" / "threshold_recidivism_binned.csv"
FIG_DIR = OUT_DIR / "figures"

PLOT_BLUE = "#1f4e79"
PLOT_TEXT = "#222222"
PLOT_MUTED = "#5f6873"
COHORTS = [
    ("1999_2008", "1999-2008: Original analysis window"),
    ("1999_2022_full4y", "1999-2022: Updated data, complete four-year follow-up"),
]


def main() -> None:
    binned = pd.read_csv(TABLE_PATH)
    fig, axes = plt.subplots(2, 1, figsize=(10.6, 10.2), sharex=True, sharey=True)

    for ax, (cohort, title) in zip(axes, COHORTS):
        data = binned[
            binned["population"].eq("adult")
            & binned["cohort"].eq(cohort)
            & binned["bac_bin"].between(0.03, 0.20, inclusive="both")
        ].sort_values("bac_bin")
        ax.scatter(data["bac_bin"], data["recid_rate"], s=25, color=PLOT_BLUE, alpha=0.85, linewidths=0)
        ax.axvline(0.08, color=PLOT_TEXT, linestyle="--", linewidth=1.2)
        ax.axvline(0.15, color="#a96819", linestyle="--", linewidth=1.2)
        ax.text(0.0815, 0.196, ".08 DUI", color=PLOT_TEXT, fontsize=10, va="top")
        ax.text(0.1515, 0.187, ".15 aggravated", color="#8b5916", fontsize=10, va="top")
        ax.set_title(title, loc="left", fontsize=14, color=PLOT_TEXT, pad=10)
        ax.set_ylabel("Repeat breath test within 4 years", color=PLOT_TEXT)
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_ylim(0.06, 0.20)
        ax.grid(axis="y", color="#d9dfe5", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines["left"].set_color("#aeb6be")
        ax.spines["bottom"].set_color("#aeb6be")
        ax.tick_params(colors=PLOT_TEXT)

    axes[-1].set_xlabel("Lower recorded BAC", color=PLOT_TEXT)
    axes[-1].set_xlim(0.03, 0.20)
    fig.suptitle("Adult BAC and Four-Year Repeat Drunk Driving", fontsize=20, fontweight="bold", color=PLOT_TEXT, y=0.975)
    fig.text(
        0.5,
        0.935,
        "Each dot is the repeat-test rate for one 0.002-BAC score bin. Vertical lines mark Washington's sanction thresholds.",
        ha="center",
        color=PLOT_MUTED,
        fontsize=10.5,
    )
    fig.tight_layout(rect=(0.04, 0.04, 0.98, 0.90))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "adult_bac_recidivism_original_vs_updated.svg", bbox_inches="tight")
    fig.savefig(FIG_DIR / "adult_bac_recidivism_original_vs_updated.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote adult BAC-recidivism comparison figures to {FIG_DIR}")


if __name__ == "__main__":
    main()
