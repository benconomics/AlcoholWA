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
- Raw observations retained after de-duplication: 1,020,285
- Retained observation dates run from 1995-11-17 through 2026-06-18

## Included exhibits

- Daily breath-test counts with a 28-day moving average
- Breath tests by day of week
- Breath tests by day of month
- Breath tests by hour of day
- Breath tests relative to turning 21
- BAC distribution with .02, .08, and .15 reference lines

## Files

- `code/analysis/rebuild_breath_bac_panel_2026.py`: full import, de-duplication,
  person identifier, repeat-offending, and exhibit pipeline.
- `code/analysis/breath_2026_descriptive_exhibits.py`: lightweight rerun script
  for aggregate exhibits from the cached de-duplicated raw parquet.
- `results/breath_panel_2026_update/tables/`: aggregate CSV tables.
- `results/breath_panel_2026_update/figures/`: SVG figures.

