# Washington Breath-Test Panel Update Through 2026

This package imports the updated Washington breath-test workbook
`2026/breathtests/R006001-040926_DB_REDACTED.xlsx`, combines it with the
previously standardized 1995-2019 breath-test extract, removes overlapping
duplicate raw observations, and produces aggregate descriptive exhibits.

Person-level raw outputs are intentionally not included in GitHub because they
contain names, DOBs, and license fields. The code can regenerate those local
files from the private Dropbox inputs.

## Duplicate audit

- Raw rows before de-duplication: 1,085,058
- Exact duplicates dropped: 137
- Instrument/date/time/citation/name duplicates dropped: 38,178
- Citation-event duplicates dropped: 26,458
- Person-time-event duplicates dropped: 0
- Cross-extract Draeger instrument/date/time/DOB duplicates dropped: 12,544
- Raw observations retained after de-duplication: 1,007,741
- Retained observation dates run from 1995-11-17 through 2026-06-18

The final cross-extract rule is necessary because the archive keeps full middle
names and a placeholder license value while the updated extract commonly has a
middle initial and no license. It is limited to Draeger observations with a
nonmissing instrument, event time, and DOB.

## Person Identifier

Recidivism uses Washington's operational composite identifier: the first five
letters of last name, first initial, middle initial, and date of birth. Fuzzy
name comparisons are audit-only: 5,763 plausible cross-key pairs and 942
near-threshold pairs were identified but are not merged into the recidivism
outcome. The non-identifying summary is in `tables/person_linkage_audit.csv`;
the detailed, name-containing review file stays local and is not published.

The completed person-day panel contains 857,608 events for 667,659 Washington
person keys, with no duplicate person-day records. Four-year repeat-offense
outcomes are complete for index tests through 2022-06-17.

## Estimation Workflow

Python imports, de-duplicates, links, and prepares the person-day panel. The
threshold RD regressions are estimated in Stata 19, not Python. After running
the Python rebuild (or `code/analysis/export_breath_rd_stata_input.py`), run:

```stata
do "2026/code/analysis/estimate_breath_threshold_rd_stata19.do"
```

Then run `code/analysis/refresh_breath_rd_outputs.py` to redraw the RD
coefficient figure and regenerate the Markdown/HTML brief from Stata's CSV
output. The Stata input contains only event date, BAC score, age, crime code,
and the four-year repeat indicator; it is local-only and excluded from GitHub.

## Included exhibits

- Daily breath-test counts with a 28-day moving average
- Breath tests by day of week
- Breath tests by day of month
- Breath tests by hour of day
- Breath-test observations relative to turning 21: daily, 7-day, and 28-day scatterplots
  for all tests, tests with BAC > 0, and tests with a recorded collision
- Age-21 scatterplots using the same three bin widths for 1999-June 2014 and
  July 2014-present; matching y-axis limits within each bin width facilitate
  descriptive comparisons across the legal-marijuana-sales break
- Recorded-collision age-21 scatterplots for 1998-June 2014 and July
  2014-present, plus Stata local-Poisson percentage-jump estimates at age 21
- BAC distribution with .02, .08, and .15 reference lines
- BAC score distribution across the full observed range, with exact-zero
  readings retained and removed, plus score-level counts around the .02, .08,
  and .15 thresholds
- Youth crime-code and Draeger-platform audit by year
- Adult (.08) and youth (.02) BAC-threshold repeat-offense exhibits for the
  1999-2008 and 1999-2022 complete-follow-up cohorts
- RD estimates of four-year repeat breath testing at adult .08/.15 and youth
  .02/.08/.15 thresholds, for the 1999-2008, 1999-2022, and 2009-2022
  cohorts, using an inclusive +/-0.05 BAC bandwidth and cluster-robust SEs
- RD estimates of four-year repeat breath testing at adult .08/.15 and youth
  .02/.08/.15 thresholds, for the 1999-2008, 1999-2022, and 2009-2022
  cohorts, using an inclusive +/-0.05 BAC bandwidth and cluster-robust SEs

## Files

- `code/analysis/rebuild_breath_bac_panel_2026.py`: full import, de-duplication,
  person identifier, repeat-offending, and exhibit pipeline.
- `code/analysis/estimate_breath_threshold_rd_stata19.do`: Stata 19 local-linear
  RD estimation with integer-BAC clustered standard errors.
- `code/analysis/refresh_breath_rd_outputs.py`: redraws the RD estimate figure
  and brief from the Stata-produced table.
- `code/analysis/build_adult_rd_social_figure.py`: creates the adult .08/.15
  social-ready confidence-interval figure from the Stata estimates.
- `code/analysis/build_adult_recidivism_scatter_comparison.py`: creates the
  vertically stacked adult BAC-recidivism comparison for the original and
  updated analysis windows.
- `code/analysis/estimate_age21_crash_rd_stata19.do`: Stata local-Poisson age-21
  crash-count models with robust delta-method percentage-jump estimates.
- `code/analysis/breath_2026_descriptive_exhibits.py`: lightweight rerun script
  for aggregate exhibits from the cached de-duplicated raw parquet.
- `results/breath_panel_2026_update/tables/`: aggregate CSV tables.
- `results/breath_panel_2026_update/figures/`: SVG figures.
- `results/breath_panel_2026_update/washington_breath_test_trends.md` and
  `.html`: short exhibit brief covering aggregate trends, age 21, and the
  pre/post-July-2014 comparison for all tests and recorded-collision tests.
- `results/breath_panel_2026_update/breath_test_rd_brief.md` and `.html`:
  breath-test figures and four-year recidivism RD estimates.
- `code/analysis/build_breath_data_quality_audit.py`: regenerates the BAC
  distribution and youth code/platform audit from the private raw panel.
- `results/breath_panel_2026_update/breath_test_rd_brief.md` and `.html`:
  breath-test figures and four-year recidivism RD estimates.
