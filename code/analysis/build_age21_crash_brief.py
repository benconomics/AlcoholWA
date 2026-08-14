from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "breath_panel_2026_update"
TABLE_PATH = OUT_DIR / "tables" / "age21_crash_rd.csv"
OUT_MD = OUT_DIR / "age21_crash_legal_access.md"
OUT_HTML = OUT_DIR / "age21_crash_legal_access.html"

PERIOD_LABELS = {
    "1998_to_june_2014": "1998-June 2014",
    "july_2014_to_present": "July 2014-present",
}


def estimate_cell(row: pd.Series) -> str:
    return f"{row['percent_jump']:+.1f}% (robust SE {row['percent_jump_se']:.1f}); p={row['p_value']:.3f}"


def main() -> None:
    estimates = pd.read_csv(TABLE_PATH).set_index("period")
    expected = set(PERIOD_LABELS)
    if set(estimates.index) != expected:
        raise ValueError(f"Expected crash estimates for {sorted(expected)}")

    md_rows = []
    html_rows = []
    for period, label in PERIOD_LABELS.items():
        row = estimates.loc[period]
        md_rows.append(f"| {label} | {estimate_cell(row)} | {int(row['n_days']):,} |")
        html_rows.append(
            f"<tr><th scope=\"row\">{escape(label)}</th><td><strong>{row['percent_jump']:+.1f}%</strong>"
            f"<br><span>Robust SE {row['percent_jump_se']:.1f}; p={row['p_value']:.3f}</span></td>"
            f"<td>{int(row['n_days']):,}</td></tr>"
        )

    md = f"""# Recorded-Collision Breath Tests Relative to Age 21

## Design

The outcome is the daily count of de-duplicated breath-test observations marked as involving a recorded collision. Each sample covers two years on either side of the tested person's 21st birthday. The first period ends in June 2014; the second begins in July 2014, when legal adult cannabis sales began in Washington.

The threshold estimates use a local Poisson count model within 90 days of age 21, with a post-21 indicator and separate linear trends on each side. The reported percentage jump is `100*(exp(beta)-1)`; standard errors use the robust delta method.

## Age-21 Crash Jump

| Period | Percentage jump at 21 | Relative-day cells |
| --- | --- | --- |
{chr(10).join(md_rows)}

## Daily Counts

| 1998-June 2014 | July 2014-present |
| --- | --- |
| ![Pre-period daily crashes relative to age 21](figures/crashes_relative_to_turning_21_1998_to_june_2014_daily.svg) | ![Post-period daily crashes relative to age 21](figures/crashes_relative_to_turning_21_july_2014_to_present_daily.svg) |

## 7-Day Bins

| 1998-June 2014 | July 2014-present |
| --- | --- |
| ![Pre-period weekly crashes relative to age 21](figures/crashes_relative_to_turning_21_1998_to_june_2014_weekly.svg) | ![Post-period weekly crashes relative to age 21](figures/crashes_relative_to_turning_21_july_2014_to_present_weekly.svg) |

## 28-Day Bins

| 1998-June 2014 | July 2014-present |
| --- | --- |
| ![Pre-period 28-day crashes relative to age 21](figures/crashes_relative_to_turning_21_1998_to_june_2014_28day.svg) | ![Post-period 28-day crashes relative to age 21](figures/crashes_relative_to_turning_21_july_2014_to_present_28day.svg) |
"""
    OUT_MD.write_text(md, encoding="utf-8")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Recorded-Collision Breath Tests Relative to Age 21</title>
<style>
:root {{ --ink:#20252b; --muted:#5f6873; --rule:#d9dfe5; --blue:#1f4e79; }}
* {{ box-sizing:border-box; }} body {{ margin:0; color:var(--ink); font-family:Arial,Helvetica,sans-serif; line-height:1.55; }}
main {{ max-width:1160px; margin:0 auto; padding:42px 28px 64px; }} h1,h2 {{ line-height:1.2; }} h1 {{ border-bottom:3px solid var(--blue); padding-bottom:20px; }} h2 {{ margin-top:42px; padding-top:12px; border-top:1px solid var(--rule); font-size:1.35rem; }}
.pair {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; margin:18px 0 28px; }} figure {{ margin:0; }} img {{ display:block; width:100%; height:auto; border:1px solid var(--rule); }}
table {{ border-collapse:collapse; width:100%; margin:18px 0 28px; }} th,td {{ border-bottom:1px solid var(--rule); padding:11px 10px; text-align:left; vertical-align:top; }} td span {{ color:var(--muted); }}
@media (max-width:760px) {{ main {{ padding:28px 18px 48px; }} .pair {{ grid-template-columns:1fr; }} }}
</style></head><body><main>
<h1>Recorded-Collision Breath Tests Relative to Age 21</h1>
<h2>Design</h2><p>The outcome is the daily count of de-duplicated breath-test observations marked as involving a recorded collision. Each sample covers two years on either side of the tested person's 21st birthday. The first period ends in June 2014; the second begins in July 2014, when legal adult cannabis sales began in Washington.</p>
<p>The threshold estimates use a local Poisson count model within 90 days of age 21, with a post-21 indicator and separate linear trends on each side. The reported percentage jump is <code>100*(exp(beta)-1)</code>; standard errors use the robust delta method.</p>
<h2>Age-21 Crash Jump</h2><table><thead><tr><th>Period</th><th>Percentage jump at 21</th><th>Relative-day cells</th></tr></thead><tbody>{''.join(html_rows)}</tbody></table>
<h2>Daily Counts</h2><div class="pair"><figure><img src="figures/crashes_relative_to_turning_21_1998_to_june_2014_daily.svg" alt="Daily recorded-collision breath tests relative to age 21, 1998 through June 2014."></figure><figure><img src="figures/crashes_relative_to_turning_21_july_2014_to_present_daily.svg" alt="Daily recorded-collision breath tests relative to age 21, July 2014 through present."></figure></div>
<h2>7-Day Bins</h2><div class="pair"><figure><img src="figures/crashes_relative_to_turning_21_1998_to_june_2014_weekly.svg" alt="Weekly recorded-collision breath tests relative to age 21, 1998 through June 2014."></figure><figure><img src="figures/crashes_relative_to_turning_21_july_2014_to_present_weekly.svg" alt="Weekly recorded-collision breath tests relative to age 21, July 2014 through present."></figure></div>
<h2>28-Day Bins</h2><div class="pair"><figure><img src="figures/crashes_relative_to_turning_21_1998_to_june_2014_28day.svg" alt="28-day recorded-collision breath tests relative to age 21, 1998 through June 2014."></figure><figure><img src="figures/crashes_relative_to_turning_21_july_2014_to_present_28day.svg" alt="28-day recorded-collision breath tests relative to age 21, July 2014 through present."></figure></div>
</main></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
