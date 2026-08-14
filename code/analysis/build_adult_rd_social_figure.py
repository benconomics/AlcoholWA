from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "breath_panel_2026_update"
TABLE_PATH = OUT_DIR / "tables" / "threshold_recidivism_rd.csv"
FIG_DIR = OUT_DIR / "figures"

PLOT_BLUE = "#1f4e79"
PLOT_TEXT = "#222222"
PLOT_MUTED = "#5f6873"
COHORTS = ["1999_2008", "1999_2022_full4y"]
COHORT_LABELS = ["1999-2008\n(original window)", "1999-2022\n(updated data)"]


def main() -> None:
    rd = pd.read_csv(TABLE_PATH)
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 7.2), sharey=True)

    for panel, (ax, threshold, title) in enumerate(zip(
        axes,
        [0.08, 0.15],
        ["BAC at or above .08", "BAC at or above .15"],
    )):
        subset = (
            rd[rd["population"].eq("adult") & rd["threshold_bac"].eq(threshold) & rd["cohort"].isin(COHORTS)]
            .set_index("cohort")
            .loc[COHORTS]
            .reset_index()
        )
        estimate = subset["coef"].to_numpy() * 100
        ci = 1.96 * subset["se"].to_numpy() * 100
        y = np.array([1, 0])

        ax.axvline(0, color=PLOT_TEXT, linewidth=1.1, zorder=1)
        ax.errorbar(estimate, y, xerr=ci, fmt="o", color=PLOT_BLUE, markersize=8, capsize=4, linewidth=2.1, zorder=3)
        for x, error, y_value in zip(estimate, ci, y):
            ax.text(
                x,
                y_value - 0.18,
                f"{x:+.2f} pp  [{x - error:+.2f}, {x + error:+.2f}]",
                ha="center",
                va="top",
                fontsize=10,
                color=PLOT_TEXT,
            )
        ax.set_xlim(-4.25, 1.25)
        ax.set_ylim(-0.55, 1.45)
        if panel == 0:
            ax.set_yticks(y, COHORT_LABELS)
        else:
            ax.tick_params(axis="y", left=False, labelleft=False)
        ax.set_title(title, fontsize=15, color=PLOT_TEXT, pad=14)
        ax.set_xlabel("Change in four-year repeat-test probability (pp)", color=PLOT_TEXT)
        ax.grid(axis="x", color="#d9dfe5", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#aeb6be")
        ax.tick_params(colors=PLOT_TEXT)

    fig.suptitle("Washington DUI sanctions and repeat offending", fontsize=22, fontweight="bold", color=PLOT_TEXT, y=0.975)
    fig.text(
        0.5,
        0.915,
        "Updated regression-discontinuity estimates: cases just above legal BAC cutoffs have lower four-year repeat breath-test rates.",
        ha="center",
        color=PLOT_MUTED,
        fontsize=11.5,
    )
    fig.text(
        0.5,
        0.035,
        "Points are estimates; bars are 95% confidence intervals. Local-linear RD, +/-0.05 BAC bandwidth; SEs clustered by BAC score.",
        ha="center",
        color=PLOT_MUTED,
        fontsize=9.5,
    )
    fig.tight_layout(rect=(0.02, 0.08, 0.98, 0.88))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "adult_threshold_rd_social.svg", bbox_inches="tight")
    fig.savefig(FIG_DIR / "adult_threshold_rd_social.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote social RD figures to {FIG_DIR}")


if __name__ == "__main__":
    main()
