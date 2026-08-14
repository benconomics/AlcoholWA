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

## Included exhibits

- Daily breath-test counts with a 28-day moving average
- Breath tests by day of week
- Breath tests by day of month
- Breath tests by hour of day
- Breath tests relative to turning 21
- BAC distribution with .02, .08, and .15 reference lines
- Adult (.08) and youth (.02) BAC-threshold repeat-offense exhibits for the
  1999-2008 and 1999-2022 complete-follow-up cohorts

## Files

- `code/analysis/rebuild_breath_bac_panel_2026.py`: full import, de-duplication,
  person identifier, repeat-offending, and exhibit pipeline.
- `code/analysis/breath_2026_descriptive_exhibits.py`: lightweight rerun script
  for aggregate exhibits from the cached de-duplicated raw parquet.
- `results/breath_panel_2026_update/tables/`: aggregate CSV tables.
- `results/breath_panel_2026_update/figures/`: SVG figures.
