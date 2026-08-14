from __future__ import annotations

import pandas as pd

from build_breath_rd_brief import main as build_brief
from rebuild_breath_bac_panel_2026 import TABLE_DIR, plot_rd_estimates


def main() -> None:
    rd = pd.read_csv(TABLE_DIR / "threshold_recidivism_rd.csv")
    plot_rd_estimates(rd)
    build_brief()
    print("Refreshed RD coefficient figure and brief from Stata estimates")


if __name__ == "__main__":
    main()
