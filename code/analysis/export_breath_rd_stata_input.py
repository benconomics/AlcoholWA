from __future__ import annotations

from rebuild_breath_bac_panel_2026 import OUT_PANEL_PARQUET, STATA_RD_INPUT, export_stata_rd_input

import pandas as pd


def main() -> None:
    panel = pd.read_parquet(OUT_PANEL_PARQUET)
    export_stata_rd_input(panel)
    print(f"Wrote non-identifying Stata RD input to {STATA_RD_INPUT}")


if __name__ == "__main__":
    main()
