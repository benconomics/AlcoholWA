version 19
clear all
set more off

* Recorded-collision breath tests relative to age 21. Python creates the daily
* count files and retains zero-count relative-day cells before this estimation.
args root
if `"`root'"' == "" local root "E:\University of Oregon Dropbox\Ben Hansen\Alcohol WA"
local out `"`root'\breath_panel_2026_update"'
local tables `"`out'\tables"'

tempfile results
postfile handle str30 period double bandwidth_days log_jump log_jump_se p_value ///
    percent_jump percent_jump_se long n_days using `results', replace

foreach period in 1998_to_june_2014 july_2014_to_present {
    import delimited using `"`tables'\tests_relative_to_21_accident_`period'_daily.csv"', clear varnames(1)
    generate byte post21 = days_to_21 >= 0
    quietly poisson tests i.post21 c.days_to_21 c.days_to_21#i.post21 if abs(days_to_21) <= 90, vce(robust)
    local log_jump = _b[1.post21]
    local log_jump_se = _se[1.post21]
    local p_value = 2 * normal(-abs(`log_jump' / `log_jump_se'))
    local percent_jump = 100 * (exp(`log_jump') - 1)
    local percent_jump_se = 100 * exp(`log_jump') * `log_jump_se'
    quietly count if abs(days_to_21) <= 90
    post handle ("`period'") (90) (`log_jump') (`log_jump_se') (`p_value') ///
        (`percent_jump') (`percent_jump_se') (r(N))
}

postclose handle
use `results', clear
export delimited using `"`tables'\age21_crash_rd.csv"', replace
display as text "Wrote `tables'\age21_crash_rd.csv"
