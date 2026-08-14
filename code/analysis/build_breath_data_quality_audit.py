from __future__ import annotations

from pathlib import Path
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "2026" / "code" / "analysis"))

from rebuild_breath_bac_panel_2026 import FIG_DIR, OUT_RAW, TABLE_DIR, clean_axes  # noqa: E402


PLOT_BLUE = "#1f4e79"
PLOT_GOLD = "#b7791f"
PLOT_OLIVE = "#6b8e23"
PLOT_TEXT = "#222222"
THRESHOLDS = [(0.02, PLOT_GOLD), (0.08, PLOT_TEXT), (0.15, PLOT_OLIVE)]


def prepare_raw() -> pd.DataFrame:
    raw = pd.read_parquet(OUT_RAW)
    raw["event_date"] = pd.to_datetime(raw["event_date"], errors="coerce").dt.normalize()
    raw["dob"] = pd.to_datetime(raw["dob"], errors="coerce").dt.normalize()
    raw["age_at_event"] = (raw["event_date"] - raw["dob"]).dt.days / 365.25
    raw["year"] = raw["event_date"].dt.year
    raw["low_score"] = raw[["alcohol1", "alcohol2"]].min(axis=1, skipna=True)
    raw["low_bac"] = pd.to_numeric(raw["low_score"], errors="coerce") / 1000
    raw["source"] = raw["source"].fillna("").astype(str).str.lower()
    return raw


def build_bac_distribution(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw[
        raw["age_at_event"].ge(18)
        & raw["crime"].isin([1, 3])
        & raw["low_score"].ge(0)
    ].copy()
    max_score = int(frame["low_score"].max())
    counts = frame.groupby("low_score").size().reindex(range(max_score + 1), fill_value=0)
    output = pd.DataFrame({"bac": counts.index / 1000, "tests_with_zero": counts.to_numpy()})
    output["tests_without_zero"] = output["tests_with_zero"]
    output.loc[output["bac"].eq(0), "tests_without_zero"] = 0
    output.to_csv(TABLE_DIR / "bac_distribution_with_without_zero.csv", index=False)
    threshold_rows = []
    for threshold_score in [20, 80, 150]:
        for crime_code in [1, 3]:
            score_counts = frame.loc[frame["crime"].eq(crime_code)].groupby("low_score").size()
            for score in range(threshold_score - 10, threshold_score + 11):
                threshold_rows.append(
                    {
                        "threshold_bac": threshold_score / 1000,
                        "crime_code": crime_code,
                        "bac": score / 1000,
                        "bac_relative_to_threshold": (score - threshold_score) / 1000,
                        "tests": int(score_counts.get(score, 0)),
                    }
                )
    pd.DataFrame(threshold_rows).to_csv(TABLE_DIR / "bac_threshold_score_counts.csv", index=False)
    return output


def plot_bac_distribution(distribution: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11.2, 8.0), sharex=True)
    for ax, column, title in [
        (axes[0], "tests_with_zero", "Including exact zero readings"),
        (axes[1], "tests_without_zero", "Excluding exact zero readings"),
    ]:
        ax.bar(distribution["bac"], distribution[column], width=0.00085, color=PLOT_BLUE)
        for threshold, color in THRESHOLDS:
            ax.axvline(threshold, color=color, linestyle="--", linewidth=1.1)
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_ylabel("Tests")
        clean_axes(ax)
    axes[1].set_xlabel("Lower recorded BAC")
    axes[1].set_xlim(0, distribution["bac"].max())
    axes[0].text(0.02, axes[0].get_ylim()[1] * 0.94, ".02", color=PLOT_GOLD, ha="center", va="top", fontsize=9)
    axes[0].text(0.08, axes[0].get_ylim()[1] * 0.94, ".08", color=PLOT_TEXT, ha="center", va="top", fontsize=9)
    axes[0].text(0.15, axes[0].get_ylim()[1] * 0.94, ".15", color=PLOT_OLIVE, ha="center", va="top", fontsize=9)
    fig.suptitle("BAC Score Distribution for Adult and Youth DUI-Related Crime Codes", y=0.995)
    fig.text(0.5, 0.01, "Ages 18+; crime codes 1 and 3; all observed BAC values shown at the 0.001 score level.", ha="center", color=PLOT_TEXT, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))
    fig.savefig(FIG_DIR / "bac_distribution_with_without_zero.svg", bbox_inches="tight")
    plt.close(fig)


def build_youth_code_audit(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    youth = raw[
        raw["age_at_event"].ge(18)
        & raw["age_at_event"].lt(21)
        & raw["crime"].isin([1, 3])
        & raw["year"].between(1999, 2025, inclusive="both")
    ].copy()
    youth["code_3"] = youth["crime"].eq(3)
    youth["draeger"] = youth["source"].eq("draeger")
    youth["exact_zero"] = youth["low_score"].eq(0)
    annual = youth.groupby("year", as_index=False).agg(
        tests=("crime", "size"),
        crime_1_tests=("crime", lambda x: int(x.eq(1).sum())),
        crime_3_tests=("crime", lambda x: int(x.eq(3).sum())),
        crime_3_share=("code_3", "mean"),
        draeger_share=("draeger", "mean"),
        exact_zero_share=("exact_zero", "mean"),
    )
    zero_by_code = (
        youth.groupby(["year", "crime"], as_index=False)["exact_zero"]
        .mean()
        .pivot(index="year", columns="crime", values="exact_zero")
        .rename(columns={1: "exact_zero_share_crime_1", 3: "exact_zero_share_crime_3"})
        .reset_index()
    )
    annual = annual.merge(zero_by_code, on="year", how="left")
    by_source = (
        youth.groupby(["year", "source", "crime"], as_index=False)
        .agg(tests=("crime", "size"), exact_zero_share=("exact_zero", "mean"), median_low_bac=("low_bac", "median"))
    )
    annual.to_csv(TABLE_DIR / "youth_crime_code_audit_by_year.csv", index=False)
    by_source.to_csv(TABLE_DIR / "youth_crime_code_audit_by_year_source.csv", index=False)
    return annual, by_source


def plot_youth_code_audit(annual: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.5))
    axes[0].plot(annual["year"], annual["crime_3_share"] * 100, color=PLOT_BLUE, linewidth=1.8, label="Crime code 3 share")
    axes[0].plot(annual["year"], annual["draeger_share"] * 100, color=PLOT_GOLD, linewidth=1.5, linestyle="--", label="Draeger share")
    axes[0].axvline(2018, color=PLOT_TEXT, linestyle=":", linewidth=1.1)
    axes[0].set_title("Youth crime-code and platform mix")
    axes[0].set_xlabel("Year")
    axes[0].set_ylabel("Share of age 18-20 tests (%)")
    axes[0].legend(frameon=False, loc="upper left")
    clean_axes(axes[0])

    axes[1].plot(annual["year"], annual["exact_zero_share_crime_1"] * 100, color=PLOT_BLUE, linewidth=1.8, label="Crime code 1")
    axes[1].plot(annual["year"], annual["exact_zero_share_crime_3"] * 100, color=PLOT_OLIVE, linewidth=1.8, label="Crime code 3")
    axes[1].axvline(2018, color=PLOT_TEXT, linestyle=":", linewidth=1.1)
    axes[1].set_title("Exact-zero BAC readings by youth crime code")
    axes[1].set_xlabel("Year")
    axes[1].set_ylabel("Share with lower BAC = 0 (%)")
    axes[1].legend(frameon=False, loc="upper left")
    clean_axes(axes[1])
    fig.suptitle("Youth Coding and Test-Platform Audit", y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "youth_crime_code_platform_audit.svg", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    raw = prepare_raw()
    distribution = build_bac_distribution(raw)
    plot_bac_distribution(distribution)
    annual, _ = build_youth_code_audit(raw)
    plot_youth_code_audit(annual)
    print(f"Wrote BAC distribution and youth coding audit to {FIG_DIR}")


if __name__ == "__main__":
    main()
