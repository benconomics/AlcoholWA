# Washington Breath-Test Trends Through 2026

## Executive Summary

- **Testing volume rose through the late 1990s, stayed high through the 2000s, and then declined.** The 2018-2019 overlap has been removed before constructing these series.
- **Breath-test observations rise sharply at age 21.** The pattern is visible at daily, weekly, and 28-day resolutions in the two years on either side of the 21st birthday.
- **The age-21 discontinuity is smaller after July 2014, when legal adult cannabis sales began in Washington.** A local-linear comparison within 90 days of age 21 estimates a 44.5% increase before the policy break and a 36.4% increase after it. This is preliminary descriptive evidence consistent with substitution, not a causal estimate.

## Aggregate Breath-Test Patterns

The figures below use de-duplicated breath-test observations from 1995 through 2026. They describe tests, not the population rate of impaired driving.

![Breath tests by date](figures/daily_tests_1995_2026.svg)

![Breath tests by day of week](figures/tests_by_day_of_week.svg)

![Breath tests by day of month](figures/tests_by_day_of_month.svg)

## Observations Relative to Turning 21

Each plot places a test by the number of days from the tested person's 21st birthday. The daily figure shows the raw day-level counts; the other two smooth that same pattern into complete 7-day and 28-day bins. Partial outer bins are excluded.

![Daily observations relative to turning 21](figures/tests_relative_to_turning_21_daily.svg)

![7-day observations relative to turning 21](figures/tests_relative_to_turning_21_weekly.svg)

![28-day observations relative to turning 21](figures/tests_relative_to_turning_21_28day.svg)

## Age-21 Count Sensitivity

The same age-21 count design is repeated after excluding zero BAC readings and then within tests with a recorded collision. These restrictions address the sharp rise in exact-zero BAC records over time and provide a smaller, potentially more consistently recorded comparison sample. Each plot uses its own vertical scale.

### BAC > 0

| Daily observations | 7-day bins | 28-day bins |
| --- | --- | --- |
| ![Daily positive-BAC observations relative to turning 21](figures/tests_relative_to_turning_21_bac_positive_daily.svg) | ![Weekly positive-BAC observations relative to turning 21](figures/tests_relative_to_turning_21_bac_positive_weekly.svg) | ![28-day positive-BAC observations relative to turning 21](figures/tests_relative_to_turning_21_bac_positive_28day.svg) |

### Recorded collision

| Daily observations | 7-day bins | 28-day bins |
| --- | --- | --- |
| ![Daily collision observations relative to turning 21](figures/tests_relative_to_turning_21_accident_daily.svg) | ![Weekly collision observations relative to turning 21](figures/tests_relative_to_turning_21_accident_weekly.svg) | ![28-day collision observations relative to turning 21](figures/tests_relative_to_turning_21_accident_28day.svg) |

## Age-21 Pattern Before and After Legal Cannabis Sales

The pre-period runs from January 1999 through June 2014. The post-period begins in July 2014 and runs through the latest available record. Within each row, the two plots use the same y-axis scale. The age-21 jump persists in both periods, but is proportionally smaller after July 2014.

### Daily observations

| 1999-June 2014 | July 2014-present |
| --- | --- |
| ![Pre-period daily age-21 observations](figures/tests_relative_to_turning_21_1999_to_june_2014_daily.svg) | ![Post-period daily age-21 observations](figures/tests_relative_to_turning_21_july_2014_to_present_daily.svg) |

### 7-day bins

| 1999-June 2014 | July 2014-present |
| --- | --- |
| ![Pre-period weekly age-21 observations](figures/tests_relative_to_turning_21_1999_to_june_2014_weekly.svg) | ![Post-period weekly age-21 observations](figures/tests_relative_to_turning_21_july_2014_to_present_weekly.svg) |

### 28-day bins

| 1999-June 2014 | July 2014-present |
| --- | --- |
| ![Pre-period 28-day age-21 observations](figures/tests_relative_to_turning_21_1999_to_june_2014_28day.svg) | ![Post-period 28-day age-21 observations](figures/tests_relative_to_turning_21_july_2014_to_present_28day.svg) |

## Interpretation and Next Steps

The difference in age-21 discontinuities is consistent with some substitution away from alcohol when legal cannabis access begins at the same threshold. Because the analysis is based on breath-test observations, the result remains sensitive to changes in testing and enforcement that differ specifically at age 21. Useful next checks are placebo age cutoffs, broader national policy variation, and California discharge data that provide an outcome outside breath-test enforcement.
