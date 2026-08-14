from __future__ import annotations

from html import escape
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "breath_panel_2026_update"
TABLE_PATH = OUT_DIR / "tables" / "threshold_recidivism_rd.csv"
OUT_MD = OUT_DIR / "breath_test_rd_brief.md"
OUT_HTML = OUT_DIR / "breath_test_rd_brief.html"

COHORTS = ["1999_2008", "1999_2022_full4y", "2009_2022_full4y"]
COHORT_LABELS = {
    "1999_2008": "1999-2008",
    "1999_2022_full4y": "1999-2022",
    "2009_2022_full4y": "2009-2022",
}


def estimate_cell(row: pd.Series) -> str:
    return f"{row['coef'] * 100:+.2f} pp ({row['se'] * 100:.2f}); N={row['n']:,}"


def estimate_cell_html(row: pd.Series) -> str:
    return (
        f"<strong>{row['coef'] * 100:+.2f} pp</strong>"
        f"<br><span class=\"detail\">SE {row['se'] * 100:.2f}; N={row['n']:,}</span>"
    )


def estimate_table(rd: pd.DataFrame, population: str, thresholds: list[float]) -> tuple[str, str]:
    subset = rd[rd["population"].eq(population)].copy()
    lookup = subset.set_index(["threshold_bac", "cohort"])
    md_rows = []
    html_rows = []
    for threshold in thresholds:
        cells = [lookup.loc[(threshold, cohort)] for cohort in COHORTS]
        md_rows.append(f"| {threshold:.2f} | " + " | ".join(estimate_cell(cell) for cell in cells) + " |")
        html_rows.append(
            "<tr>"
            f"<th scope=\"row\">{threshold:.2f}</th>"
            + "".join(f"<td>{estimate_cell_html(cell)}</td>" for cell in cells)
            + "</tr>"
        )
    header = "| BAC threshold | " + " | ".join(COHORT_LABELS[cohort] for cohort in COHORTS) + " |"
    divider = "| --- | " + " | ".join("---" for _ in COHORTS) + " |"
    md_table = "\n".join([header, divider, *md_rows])
    html_table = """<div class=\"table-wrap\"><table>
  <thead><tr><th>BAC threshold</th>""" + "".join(
        f"<th>{escape(COHORT_LABELS[cohort])}</th>" for cohort in COHORTS
    ) + "</tr></thead>\n  <tbody>" + "\n".join(html_rows) + "</tbody>\n</table></div>"
    return md_table, html_table


def main() -> None:
    rd = pd.read_csv(TABLE_PATH)
    required = {
        ("adult", threshold, cohort)
        for threshold in [0.08, 0.15]
        for cohort in COHORTS
    } | {
        ("youth", threshold, cohort)
        for threshold in [0.02, 0.08, 0.15]
        for cohort in COHORTS
    }
    observed = set(zip(rd["population"], rd["threshold_bac"], rd["cohort"]))
    missing = required - observed
    if missing:
        raise ValueError(f"Missing requested RD estimates: {sorted(missing)}")
    if not np.isclose(rd["bandwidth_bac"], 0.05).all():
        raise ValueError("The brief requires an inclusive +/-0.05 BAC bandwidth.")

    adult_md, adult_html = estimate_table(rd, "adult", [0.08, 0.15])
    youth_md, youth_html = estimate_table(rd, "youth", [0.02, 0.08, 0.15])

    md = f"""# Washington Breath Tests and Four-Year Recidivism RD Estimates

## Summary

- **Adult thresholds show lower four-year repeat breath-test rates just above both BAC cutoffs.** At .08, the estimated discontinuity is -2.58 percentage points in 1999-2008, -2.08 points in 1999-2022, and -1.85 points in 2009-2022.
- **At the adult .15 aggravated-DUI threshold, the estimated discontinuity is smaller but still negative across all three cohorts.**
- **For drivers younger than 21, the .02 discontinuity is negative in the earlier and longer cohorts but is imprecise in the 2009-2022 cohort.** The .08 and .15 youth estimates are also imprecise.

## BAC Distribution and Sorting Check

The first exhibit plots the lower recorded BAC for ages 18 and older in crime codes 1 and 3 across the full observed BAC range. The upper panel includes exact-zero readings; the lower panel removes them so the score distribution near the legal thresholds is visible. The figure does not show an isolated point mass at .02, .08, or .15, but it should be interpreted alongside the coding audit below.

![BAC distribution with and without zero](figures/bac_distribution_with_without_zero.svg)

## Breath-Test Patterns

The descriptive figures use de-duplicated Washington breath-test observations from 1995 through 2026.

![Breath tests by date](figures/daily_tests_1995_2026.svg)

| By day of week | By day of month |
| --- | --- |
| ![Breath tests by day of week](figures/tests_by_day_of_week.svg) | ![Breath tests by day of month](figures/tests_by_day_of_month.svg) |

## Youth Coding and Test-Platform Audit

The youth analytic sample includes crime codes 1 and 3. Draeger accounts for 56.1% of youth observations in 2017, 98.1% in 2018, and essentially all observations from 2019 forward. Code 3's share falls from 21.1% in 2017 to 18.9% in 2018 and 15.8% in 2019: this is not an all-at-once recode, but the code mix is not time-invariant. Exact-zero lower BAC readings rise sharply for code 1 at the platform transition (2.9% in 2017, 9.1% in 2018, and 14.2% in 2019), while code 3 does not show the same spike. Post-2018 youth specifications should therefore be checked with and without exact-zero readings and by crime code.

![Youth crime code and platform audit](figures/youth_crime_code_platform_audit.svg)

## RD Design

Each model estimates a local-linear regression discontinuity in the probability of a subsequent breath test within four years. The running variable is the lower recorded BAC, and the treatment indicator turns on at the stated BAC threshold. The estimation window includes observations within +/-0.05 BAC points of the cutoff. Standard errors are cluster-robust by integer BAC score. The 1999-2022 and 2009-2022 cohorts include only index tests with complete four-year follow-up; 2022 therefore ends on June 17.

Adults are age 21 and older with the adult DUI crime code. Youth are ages 18-20 with the applicable adult or under-21 code. Estimates are percentage-point discontinuities; standard errors and sample sizes appear in parentheses and after the semicolon.

![Adult RD point estimates](figures/adult_threshold_rd_estimates_h0p05.svg)

![Youth RD point estimates](figures/youth_threshold_rd_estimates_h0p05.svg)

## BAC and Four-Year Recidivism Scatterplots

Each point is a 0.001-BAC cell; circle size is proportional to the number of index tests in the cell. These displays retain broader BAC ranges for visual context, whereas the tabled RD models use the stated +/-0.05 bandwidth around each threshold.

![Adult BAC and repeat testing](figures/adult_threshold_recidivism.svg)

![Adult BAC and repeat testing, 2009-2022](figures/adult_threshold_recidivism_2009_2022.svg)

![Youth BAC and repeat testing](figures/youth_threshold_recidivism.svg)

## Adults: Four-Year Repeat Breath Test

{adult_md}

## Youth Ages 18-20: Four-Year Repeat Breath Test

{youth_md}

## Interpretation

The estimates are local associations around administrative BAC thresholds, not estimates of the effect of alcohol consumption itself. A negative coefficient means that otherwise comparable observations just above the threshold have a lower estimated probability of another breath test within four years. The adult estimates are consistently negative; the youth models have substantially less precision, especially in the later cohort.

The source table is `tables/threshold_recidivism_rd.csv`.
"""
    OUT_MD.write_text(md, encoding="utf-8")

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta name=\"color-scheme\" content=\"light dark\">
  <title>Washington Breath Tests and Four-Year Recidivism RD Estimates</title>
  <style>
    :root {{ color-scheme: light dark; --paper: #fff; --ink: #20252b; --muted: #5f6873; --rule: #d9dfe5; --blue: #1f4e79; --blue-soft: #edf3f8; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --paper: #171b20; --ink: #f1f4f6; --muted: #b4bec7; --rule: #3a434d; --blue: #9cc6ed; --blue-soft: #222c35; }} }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); font-family: Arial, Helvetica, sans-serif; line-height: 1.55; }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 42px 28px 64px; }}
    header {{ border-bottom: 3px solid var(--blue); padding-bottom: 20px; }}
    h1, h2 {{ line-height: 1.2; margin: 0; }}
    h1 {{ font-size: 2rem; }}
    h2 {{ font-size: 1.35rem; margin-top: 42px; padding-top: 12px; border-top: 1px solid var(--rule); }}
    p {{ margin: 12px 0; }}
    .scope, .detail, .note {{ color: var(--muted); }}
    .summary {{ margin-top: 22px; padding: 18px 20px; background: var(--blue-soft); border-left: 4px solid var(--blue); }}
    .summary h2 {{ border: 0; margin: 0 0 10px; padding: 0; font-size: 1.05rem; }}
    ul {{ margin: 0; padding-left: 20px; }}
    li + li {{ margin-top: 8px; }}
    figure {{ margin: 20px 0 30px; }}
    img {{ display: block; width: 100%; height: auto; border: 1px solid var(--rule); background: #fff; }}
    figcaption {{ color: var(--muted); font-size: .92rem; margin-top: 6px; }}
    .pair {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin: 16px 0 28px; }}
    .pair figure {{ margin: 0; }}
    .table-wrap {{ overflow-x: auto; margin: 18px 0 28px; }}
    table {{ border-collapse: collapse; min-width: 780px; width: 100%; font-size: .94rem; }}
    th, td {{ border-bottom: 1px solid var(--rule); padding: 11px 10px; text-align: left; vertical-align: top; }}
    thead th {{ color: var(--blue); border-bottom: 2px solid var(--blue); }}
    tbody th {{ white-space: nowrap; }}
    footer {{ border-top: 1px solid var(--rule); color: var(--muted); font-size: .9rem; margin-top: 42px; padding-top: 16px; }}
    @media (max-width: 760px) {{ main {{ padding: 28px 18px 48px; }} h1 {{ font-size: 1.65rem; }} .pair {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Washington Breath Tests and Four-Year Recidivism RD Estimates</h1>
      <p class=\"scope\">De-duplicated observations; local-linear BAC-threshold models with inclusive +/-0.05 bandwidths</p>
    </header>
    <section class=\"summary\" aria-labelledby=\"summary-heading\">
      <h2 id=\"summary-heading\">Executive Summary</h2>
      <ul>
        <li><strong>Adult thresholds show lower four-year repeat breath-test rates just above both BAC cutoffs.</strong> At .08, the estimated discontinuity is -2.58 percentage points in 1999-2008, -2.08 points in 1999-2022, and -1.85 points in 2009-2022.</li>
        <li><strong>At the adult .15 aggravated-DUI threshold, the estimated discontinuity is smaller but still negative across all three cohorts.</strong></li>
        <li><strong>For drivers younger than 21, the .02 discontinuity is negative in the earlier and longer cohorts but is imprecise in the 2009-2022 cohort.</strong> The .08 and .15 youth estimates are also imprecise.</li>
      </ul>
    </section>
    <section aria-labelledby=\"distribution-heading\">
      <h2 id=\"distribution-heading\">BAC Distribution and Sorting Check</h2>
      <p>The first exhibit plots the lower recorded BAC for ages 18 and older in crime codes 1 and 3 across the full observed BAC range. The upper panel includes exact-zero readings; the lower panel removes them so the score distribution near the legal thresholds is visible. The figure does not show an isolated point mass at .02, .08, or .15, but it should be read alongside the coding audit below.</p>
      <figure><img src=\"figures/bac_distribution_with_without_zero.svg\" alt=\"BAC score distribution with exact zero readings included and excluded, marking the .02, .08, and .15 thresholds.\"><figcaption>BAC score distribution at the 0.001 BAC score level.</figcaption></figure>
    </section>
    <section aria-labelledby=\"tests-heading\">
      <h2 id=\"tests-heading\">Breath-Test Patterns</h2>
      <p>These descriptive figures use de-duplicated Washington breath-test observations from 1995 through 2026.</p>
      <figure><img src=\"figures/daily_tests_1995_2026.svg\" alt=\"Daily Washington breath tests and a 28-day moving average from 1995 through 2026.\"><figcaption>Breath tests by date.</figcaption></figure>
      <div class=\"pair\">
        <figure><img src=\"figures/tests_by_day_of_week.svg\" alt=\"Washington breath tests by day of week.\"><figcaption>Breath tests by day of week.</figcaption></figure>
        <figure><img src=\"figures/tests_by_day_of_month.svg\" alt=\"Washington breath tests by day of month.\"><figcaption>Breath tests by day of month.</figcaption></figure>
      </div>
    </section>
    <section aria-labelledby=\"audit-heading\">
      <h2 id=\"audit-heading\">Youth Coding and Test-Platform Audit</h2>
      <p>The youth analytic sample includes crime codes 1 and 3. Draeger accounts for 56.1% of youth observations in 2017, 98.1% in 2018, and essentially all observations from 2019 forward. Code 3's share falls from 21.1% in 2017 to 18.9% in 2018 and 15.8% in 2019: this is not an all-at-once recode, but the code mix is not time-invariant. Exact-zero lower BAC readings rise sharply for code 1 at the platform transition (2.9% in 2017, 9.1% in 2018, and 14.2% in 2019), while code 3 does not show the same spike. Post-2018 youth specifications should therefore be checked with and without exact-zero readings and by crime code.</p>
      <figure><img src=\"figures/youth_crime_code_platform_audit.svg\" alt=\"Annual youth crime code and test-platform composition, alongside exact-zero BAC shares by crime code.\"><figcaption>Youth code mix, Draeger coverage, and exact-zero readings.</figcaption></figure>
    </section>
    <section aria-labelledby=\"design-heading\">
      <h2 id=\"design-heading\">RD Design and Point Estimates</h2>
      <p>Each local-linear model estimates the discontinuity in the probability of a subsequent breath test within four years at the stated BAC cutoff. The running variable is the lower recorded BAC. The window includes observations within +/-0.05 BAC points; standard errors are cluster-robust by integer BAC score. The longer cohorts include only index tests with complete four-year follow-up, so 2022 ends on June 17.</p>
      <div class=\"pair\">
        <figure><img src=\"figures/adult_threshold_rd_estimates_h0p05.svg\" alt=\"Adult BAC threshold regression discontinuity point estimates with 95 percent confidence intervals.\"><figcaption>Adults ages 21 and older.</figcaption></figure>
        <figure><img src=\"figures/youth_threshold_rd_estimates_h0p05.svg\" alt=\"Youth BAC threshold regression discontinuity point estimates with 95 percent confidence intervals.\"><figcaption>Youth ages 18-20.</figcaption></figure>
      </div>
    </section>
    <section aria-labelledby=\"scatter-heading\">
      <h2 id=\"scatter-heading\">BAC and Four-Year Recidivism Scatterplots</h2>
      <p>Each point is a 0.001-BAC cell; circle size is proportional to the number of index tests in the cell. These displays retain broader BAC ranges for visual context, whereas the tabled RD models use the stated +/-0.05 bandwidth around each threshold.</p>
      <figure><img src=\"figures/adult_threshold_recidivism.svg\" alt=\"Adult BAC and four-year repeat breath testing scatterplots for the 1999-2008 and 1999-2022 cohorts.\"><figcaption>Adults ages 21 and older: 1999-2008 and 1999-2022 cohorts.</figcaption></figure>
      <figure><img src=\"figures/adult_threshold_recidivism_2009_2022.svg\" alt=\"Adult BAC and four-year repeat breath testing scatterplot for the 2009-2022 cohort.\"><figcaption>Adults ages 21 and older: 2009-2022 cohort.</figcaption></figure>
      <figure><img src=\"figures/youth_threshold_recidivism.svg\" alt=\"Youth BAC and four-year repeat breath testing scatterplots for the 1999-2008 and 1999-2022 cohorts.\"><figcaption>Youth ages 18-20: 1999-2008 and 1999-2022 cohorts.</figcaption></figure>
    </section>
    <section aria-labelledby=\"adult-heading\">
      <h2 id=\"adult-heading\">Adults: Four-Year Repeat Breath Test</h2>
      <p class=\"note\">Estimates are percentage-point discontinuities. Each cell gives point estimate, cluster-robust standard error, and analytic sample size.</p>
      {adult_html}
    </section>
    <section aria-labelledby=\"youth-heading\">
      <h2 id=\"youth-heading\">Youth Ages 18-20: Four-Year Repeat Breath Test</h2>
      <p class=\"note\">The .02 youth models have less left-side support because BAC is bounded below at zero; interpret their larger bandwidth results with particular care.</p>
      {youth_html}
    </section>
    <section aria-labelledby=\"interpretation-heading\">
      <h2 id=\"interpretation-heading\">Interpretation</h2>
      <p>The estimates are local associations around administrative BAC thresholds, not estimates of the effect of alcohol consumption itself. A negative coefficient means that otherwise comparable observations just above the threshold have a lower estimated probability of another breath test within four years. The adult estimates are consistently negative; the youth models have substantially less precision, especially in the later cohort.</p>
    </section>
    <footer>Source: <code>tables/threshold_recidivism_rd.csv</code>. Four-year recidivism is a subsequent qualifying breath-test observation within 1,462 days.</footer>
  </main>
</body>
</html>
"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
