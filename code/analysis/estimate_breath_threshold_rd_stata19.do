version 19
clear all
set more off

* Python creates this non-identifying Stata input after cleaning and linkage.
* Set this root once if the project is stored elsewhere.
args root
if `"`root'"' == "" local root "E:\University of Oregon Dropbox\Ben Hansen\Alcohol WA"
local out `"`root'\breath_panel_2026_update"'
local input `"`out'\stata_inputs\breath_panel_rd_input.dta"'
local tables `"`out'\tables"'

capture mkdir `"`tables'"'
use `"`input'"', clear
format event_date %td

quietly summarize event_date, meanonly
local full_followup_cutoff = r(max) - 1462
local full_sample_end = min(date("2022-12-31", "YMD"), `full_followup_cutoff')

tempfile results
postfile handle str8 population str20 cohort double threshold_bac bandwidth_bac ///
    long n clusters str40 se_type double coef se p_value mean_below mean_above ///
    using `results', replace

foreach population in adult youth {
    if "`population'" == "adult" local thresholds "80 150"
    else local thresholds "20 80 150"

    foreach cohort in 1999_2008 1999_2022_full4y 2009_2022_full4y {
        local start = cond("`cohort'" == "2009_2022_full4y", date("2009-01-01", "YMD"), date("1999-01-01", "YMD"))
        local end = cond("`cohort'" == "1999_2008", date("2008-12-31", "YMD"), `full_sample_end')

        foreach threshold of local thresholds {
            preserve
            keep if !missing(event_date, low_score, age_at_event, crime, recidivism_4y_wa)
            keep if inrange(event_date, `start', `end') & event_date <= `full_followup_cutoff'
            keep if inlist(crime, 1, 3)
            if "`population'" == "adult" {
                keep if age_at_event >= 21 & crime == 1 & inrange(low_score, 30, 200)
            }
            else {
                keep if age_at_event >= 18 & age_at_event < 21 & inrange(low_score, 0, 200)
            }

            generate double running = low_score - `threshold'
            generate byte above = low_score >= `threshold'
            generate double above_running = above * running
            quietly count if abs(running) <= 50
            local n = r(N)
            quietly levelsof low_score if abs(running) <= 50, local(scores)
            local clusters : word count `scores'
            local coef = .
            local se = .
            local p_value = .
            local mean_below = .
            local mean_above = .

            quietly regress recidivism_4y_wa above running above_running if abs(running) <= 50, vce(cluster low_score)
            if !_rc {
                local coef = _b[above]
                local se = _se[above]
                local p_value = 2 * ttail(e(df_r), abs(`coef' / `se'))
                quietly summarize recidivism_4y_wa if low_score == `threshold' - 1, meanonly
                local mean_below = r(mean)
                quietly summarize recidivism_4y_wa if low_score == `threshold', meanonly
                local mean_above = r(mean)
            }
            post handle ("`population'") ("`cohort'") (`threshold' / 1000) (0.05) ///
                (`n') (`clusters') ("Cluster-robust by integer BAC score") ///
                (`coef') (`se') (`p_value') (`mean_below') (`mean_above')
            restore
        }
    }
}

postclose handle
use `results', clear
sort population threshold_bac cohort
export delimited using `"`tables'\threshold_recidivism_rd.csv"', replace
display as text "Wrote `tables'\threshold_recidivism_rd.csv"
