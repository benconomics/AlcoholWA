from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "2026" / "code" / "analysis"))

from rebuild_breath_bac_panel_2026 import (  # noqa: E402
    FIG_DIR,
    OUT_RAW,
    TABLE_DIR,
    plot_descriptives,
    prepare_raw_descriptive_observations,
    time_to_seconds,
)


PLOT_BLUE = "#1f4e79"
PLOT_TEXT = "#222222"


def clean_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=PLOT_TEXT)


def build_tables(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    desc = prepare_raw_descriptive_observations(raw)
    daily = desc.groupby("event_date", as_index=False).size().rename(columns={"size": "tests"})
    daily["tests_28d_ma"] = daily["tests"].rolling(28, min_periods=1, center=True).mean()
    dow = desc.groupby("dow", observed=False, as_index=False).size().rename(columns={"size": "tests"})
    dom = desc.groupby("day_of_month", as_index=False).size().rename(columns={"size": "tests"})
    hour = desc.dropna(subset=["hour"]).groupby("hour", as_index=False).size().rename(columns={"size": "tests"})
    around21 = desc[desc["days_to_21"].between(-730, 730, inclusive="both")].copy()
    around21["days_to_21_bin"] = np.floor(around21["days_to_21"] / 30) * 30
    age21 = around21.groupby("days_to_21_bin", as_index=False).size().rename(columns={"size": "tests"})
    source_years = (
        raw.groupby(["source_extract", "source", raw["event_date"].dt.year], as_index=False)
        .size()
        .rename(columns={"event_date": "year", "size": "rows"})
    )
    outputs = {
        "daily_tests": daily,
        "tests_by_day_of_week": dow,
        "tests_by_day_of_month": dom,
        "tests_by_hour": hour,
        "tests_relative_to_21": age21,
        "source_years_after_dedup": source_years,
    }
    for name, frame in outputs.items():
        frame.to_csv(TABLE_DIR / f"{name}.csv", index=False)
    return outputs


def plot_bac_distribution(raw: pd.DataFrame) -> None:
    frame = raw.copy()
    frame["low_score"] = frame[["alcohol1", "alcohol2"]].min(axis=1, skipna=True)
    frame["low_bac"] = pd.to_numeric(frame["low_score"], errors="coerce") / 1000
    frame = frame[frame["low_bac"].between(0, 0.30, inclusive="both")].copy()
    frame["bac_bin"] = np.floor(frame["low_bac"] * 1000) / 1000
    binned = frame.groupby("bac_bin", as_index=False).size().rename(columns={"size": "tests"})
    binned.to_csv(TABLE_DIR / "bac_distribution.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(binned["bac_bin"], binned["tests"], width=0.00085, color=PLOT_BLUE)
    for threshold in [0.02, 0.08, 0.15]:
        ax.axvline(threshold, color=PLOT_TEXT, linestyle="--", linewidth=1.0)
    ax.set_title("Breath-Test BAC Distribution")
    ax.set_xlabel("BAC")
    ax.set_ylabel("Tests")
    ax.set_xlim(0, 0.30)
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bac_distribution.svg", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(OUT_RAW)
    raw["event_date"] = pd.to_datetime(raw["event_date"], errors="coerce").dt.normalize()
    tables = build_tables(raw)
    plot_descriptives(tables)
    plot_bac_distribution(raw)
    print(f"Wrote descriptive exhibits to {FIG_DIR}")


if __name__ == "__main__":
    main()
