from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from breath_bac_recidivism_linkage import (
    BAC_MAX,
    BAC_MIN,
    DATE_WINDOW_DAYS,
    FOLLOWUP_COHORT_END_YEAR,
    LEGAL_AGE,
    OUT_BINNED,
    OUT_FIG,
    OUT_LINKED,
    OUT_MATCH_SUMMARY,
    OUT_MD,
    PLOT_GROUPS,
    build_binned_summary,
    make_date_candidates,
    normalize_text,
    parse_breath_name,
    pick_best_matches,
    plot_scatter_panels,
    prepare_court_panel,
    score_candidates,
)


ROOT = Path(__file__).resolve().parents[3]
RAW_BREATH_CSV_PATH = ROOT / "Older" / "breath_test_10_2016.csv"
LEGACY_ANALYSIS_PATH = ROOT / "Older" / "dui_analysis.dta"
OUT_DIR = ROOT / "breath_bac_recidivism_linkage"
OUT_PANEL = OUT_DIR / "rebuilt_dui_analysis_panel.csv.gz"
OUT_SOURCE_SUMMARY = OUT_DIR / "rebuilt_breath_source_by_year.csv"
OUT_COMPARE_YEAR = OUT_DIR / "rebuilt_vs_saved_dui_panel_by_year.csv"
OUT_COMPARE_SUMMARY = OUT_DIR / "rebuilt_vs_saved_dui_panel_summary.csv"

MIN_ANALYSIS_DATE = pd.Timestamp("1999-01-01")
BAD_SUBJECT_NAMES = {
    normalize_text(name)
    for name in [
        "AAA",
        "TEST",
        "NEW/SOLUTION",
        "TEST/NEW/SOLUTION",
        "NEW/SOL",
        "SOLUTION/CHANGE",
        "UNKNOWN",
        "NEWSOLUTION",
        "TEST/TEST/TEST",
        "M",
        "F",
        "SOLUTION",
        "JOHN/DOE",
        "SOLUTIONCHANGE",
        "TEST/TEST/T",
        "TEST/TEST",
        "TEST/JOHN/DOE",
        "TEST/DOE/JOHN",
        "AAAAAAAA",
        "NEW/SOLUTION/TEST",
        "DOE/JOHN",
        "DOE/JOHN/J",
        "DOE/JOHN/Q",
        "DOE/JOHN/A",
        "DOE/JOHN/D",
        "TEST/NEW/SOLUTION/QA",
        "A",
        "A/A/A",
        "AA/AA",
        "A/M/K",
        "AA/AA/TEST",
        "AAAA",
        "AABCDEF",
        "ZZZZZ/Z/Z",
        "ZZZ",
        "BLOW/JOE/Z",
        "BLOW/JOE/E",
        "TEST, TEST T",
        "AS FOUND, AS FOUND AS FOUND",
        "SAMPLE",
        "SELT/TEST",
        "BBBBB BBBBBB, BBBBBBBB BBB",
        "WILSON/RITA/W",
        "BIRD/JOHN/JOAQUIN",
        "TEST, TEST TEST",
        "DOE, MARK JAMES",
    ]
}

CSV_COLUMNS = [
    "InstrumentSerialNumber",
    "BreathTestDate",
    "CitationCaseNumber",
    "OperatorName",
    "OperatorAgencyCode",
    "SubjectName",
    "SubjectDateOfBirth",
    "SubjectGender",
    "SubjectEthnicGroup",
    "CountyOfArrest",
    "CrimeCode",
    "CollisionIndicator",
    "DrinkingLocation",
    "Test1BreathAlcoholReading",
    "Test2BreathAlcoholReadingIR",
]


def split_subject_name(value: object) -> list[str]:
    raw = "" if pd.isna(value) else str(value).strip()
    raw = raw.replace(",", "/")
    parts = [part.strip().upper() for part in raw.split("/") if part.strip()]
    while len(parts) < 4:
        parts.append("")
    return parts[:4]


def build_person_id_key(
    last_name: pd.Series,
    first_name: pd.Series,
    dob: pd.Series,
    sex: pd.Series,
) -> pd.Series:
    # Middle initials are often present on one event and absent on another.
    # Omitting them avoids splitting the same person across repeat events.
    return (
        last_name.fillna("").astype(str)
        + "|"
        + first_name.fillna("").astype(str)
        + "|"
        + pd.to_datetime(dob, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        + "|"
        + sex.fillna("").astype(str).str.upper().str[:1]
    )


def annual_raw_counts() -> pd.DataFrame:
    rows: list[dict[str, int]] = []
    for year in range(1995, 2012):
        path = ROOT / "Older" / f"alcohol_{year}.dta"
        frame = pd.read_stata(path, convert_categoricals=False, columns=["Date"])
        rows.append({"year": year, "annual_raw_rows": int(len(frame))})

    late = pd.read_stata(ROOT / "Older" / "alcohol_2014.dta", convert_categoricals=False, columns=["date"])
    late_years = pd.to_datetime(late["date"], errors="coerce").dt.year.value_counts().sort_index()
    for year, count in late_years.items():
        rows.append({"year": int(year), "annual_raw_rows": int(count)})

    return pd.DataFrame(rows).groupby("year", as_index=False)["annual_raw_rows"].sum()


def build_rebuilt_panel() -> pd.DataFrame:
    csv = pd.read_csv(RAW_BREATH_CSV_PATH, usecols=CSV_COLUMNS, low_memory=False)
    panel = pd.DataFrame(
        {
            "SerialNo": csv["InstrumentSerialNumber"],
            "Date": pd.to_datetime(csv["BreathTestDate"], errors="coerce").dt.normalize(),
            "Citation": csv["CitationCaseNumber"].fillna(""),
            "Operator": csv["OperatorName"].fillna(""),
            "Agency": csv["OperatorAgencyCode"].fillna(""),
            "SubjectName": csv["SubjectName"].fillna(""),
            "Sex": csv["SubjectGender"].fillna(""),
            "EthnicGroup": csv["SubjectEthnicGroup"].fillna(""),
            "County": pd.to_numeric(csv["CountyOfArrest"], errors="coerce"),
            "crime": pd.to_numeric(csv["CrimeCode"], errors="coerce"),
            "Accident": csv["CollisionIndicator"].fillna(""),
            "Location": csv["DrinkingLocation"].fillna(""),
            "Alcohol1char": "",
            "Alcohol1": pd.to_numeric(csv["Test1BreathAlcoholReading"], errors="coerce").mul(1000).round(),
            "Alcohol2char": "",
            "Alcohol2": pd.to_numeric(csv["Test2BreathAlcoholReadingIR"], errors="coerce").mul(1000).round(),
            "dob": pd.to_datetime(csv["SubjectDateOfBirth"], errors="coerce").dt.normalize(),
            "License": "",
        }
    )
    panel["subject_name_clean"] = panel["SubjectName"].map(normalize_text)
    panel["operator_clean"] = panel["Operator"].map(normalize_text)
    panel = panel[
        panel["Date"].notna()
        & panel["dob"].notna()
        & panel["crime"].notna()
        & panel["subject_name_clean"].ne("")
        & ~panel["subject_name_clean"].isin(BAD_SUBJECT_NAMES)
        & ~panel["subject_name_clean"].eq(panel["operator_clean"])
    ].copy()

    parts = panel["SubjectName"].map(split_subject_name)
    name_parts = pd.DataFrame(parts.tolist(), index=panel.index, columns=["SubjectName1", "SubjectName2", "SubjectName3", "SubjectName4"])
    panel = pd.concat([panel, name_parts], axis=1)
    panel = panel[~panel["SubjectName1"].isin(["TEST", "NEW"])].copy()

    panel["SubjectName2"] = np.where(panel["SubjectName2"].eq(""), panel["SubjectName3"], panel["SubjectName2"])
    panel["SubjectName3"] = np.where(panel["SubjectName3"].eq(""), panel["SubjectName4"], panel["SubjectName3"])
    panel["SubjectName2"] = panel["SubjectName2"].where(panel["SubjectName2"].ne(""), "A")
    panel["middle"] = panel["SubjectName3"].str[:1]
    panel["middle"] = panel["middle"].where(panel["middle"].ne(""), "A")

    panel = panel.drop_duplicates().copy()
    panel["id_key"] = build_person_id_key(
        panel["SubjectName1"],
        panel["SubjectName2"],
        panel["dob"],
        panel["Sex"],
    )
    panel["id"] = pd.factorize(panel["id_key"], sort=False)[0] + 1

    panel.loc[(panel["Alcohol1"] > 0) & panel["Alcohol2"].fillna(0).eq(0), "Alcohol2"] = np.nan
    panel.loc[(panel["Alcohol1"].fillna(0).eq(0)) & (panel["Alcohol2"] > 0), "Alcohol2"] = np.nan

    same_day = panel.groupby(["id", "Date"], sort=False)
    panel["Alcohol1"] = same_day["Alcohol1"].transform("min")
    panel["Alcohol2"] = same_day["Alcohol2"].transform("min")
    panel = panel.sort_values(["id", "Date", "SerialNo", "Citation"]).drop_duplicates(["id", "Date"], keep="first").copy()

    panel["offense"] = panel.groupby("id").cumcount() + 1
    panel["total_dui"] = panel.groupby("id")["offense"].transform("max") - 1
    panel["low_score"] = panel[["Alcohol1", "Alcohol2"]].min(axis=1, skipna=True)
    panel = panel[panel["Date"] > MIN_ANALYSIS_DATE].copy()
    panel["low_score_mod"] = np.where(panel["low_score"].notna(), panel["low_score"] - np.mod(panel["low_score"], 2), np.nan)
    panel["year"] = panel["Date"].dt.year
    panel["male"] = panel["Sex"].astype(str).str.upper().eq("M").astype(int)
    panel["white"] = panel["EthnicGroup"].astype(str).str.upper().eq("W").astype(int)

    panel["acc_fut"] = panel.groupby("id")["Accident"].shift(-1).fillna("")
    panel["recid_date"] = panel.groupby("id")["Date"].shift(-1)
    panel["recid_bac"] = panel.groupby("id")["low_score"].shift(-1)
    panel["refusal1"] = ""
    panel["refusal2"] = ""

    days_to_next = (panel["recid_date"] - panel["Date"]).dt.days
    panel["recidivism"] = ((days_to_next <= 1462) & (days_to_next > 0)).astype(int)
    panel["acc_recid"] = ((panel["recidivism"] == 1) & panel["acc_fut"].astype(str).str.upper().eq("Y")).astype(int)
    panel["diff"] = panel["Alcohol1"] - panel["Alcohol2"]

    panel = panel[panel["crime"].eq(1) & ~(panel["Alcohol1"].isna() & panel["Alcohol2"].isna())].copy()
    return panel[
        [
            "SerialNo",
            "Date",
            "Citation",
            "Operator",
            "Agency",
            "SubjectName",
            "Sex",
            "EthnicGroup",
            "County",
            "crime",
            "Accident",
            "Alcohol1char",
            "Alcohol1",
            "Alcohol2",
            "Location",
            "Alcohol2char",
            "SubjectName1",
            "SubjectName2",
            "SubjectName3",
            "SubjectName4",
            "dob",
            "License",
            "middle",
            "id",
            "offense",
            "total_dui",
            "low_score",
            "low_score_mod",
            "male",
            "white",
            "year",
            "acc_fut",
            "recid_date",
            "recid_bac",
            "refusal1",
            "refusal2",
            "recidivism",
            "acc_recid",
            "diff",
        ]
    ].copy()


def load_saved_panel() -> pd.DataFrame:
    cols = [
        "SerialNo",
        "Date",
        "Citation",
        "Operator",
        "Agency",
        "SubjectName",
        "Sex",
        "EthnicGroup",
        "County",
        "crime",
        "Accident",
        "Alcohol1char",
        "Alcohol1",
        "Alcohol2",
        "Location",
        "Alcohol2char",
        "dob",
        "License",
        "offense",
        "total_dui",
        "low_score",
        "low_score_mod",
        "year",
        "recid_date",
        "recid_bac",
        "recidivism",
        "diff",
    ]
    saved = pd.read_stata(LEGACY_ANALYSIS_PATH, convert_categoricals=False, columns=cols)
    saved["Date"] = pd.to_datetime(saved["Date"], errors="coerce").dt.normalize()
    saved["dob"] = pd.to_datetime(saved["dob"], errors="coerce").dt.normalize()
    saved["recid_date"] = pd.to_datetime(saved["recid_date"], errors="coerce").dt.normalize()
    saved["crime"] = pd.to_numeric(saved["crime"], errors="coerce")
    saved["low_score"] = pd.to_numeric(saved["low_score"], errors="coerce")
    saved["low_score_mod"] = pd.to_numeric(saved["low_score_mod"], errors="coerce")
    saved["recid_bac"] = pd.to_numeric(saved["recid_bac"], errors="coerce")
    saved["recidivism"] = pd.to_numeric(saved["recidivism"], errors="coerce").fillna(0).astype(int)
    saved["offense"] = pd.to_numeric(saved["offense"], errors="coerce")
    saved["year"] = pd.to_numeric(saved["year"], errors="coerce")
    return saved


def prepare_analysis_sample(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["event_date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["dob_date"] = pd.to_datetime(frame["dob"], errors="coerce").dt.normalize()
    frame["recid_date"] = pd.to_datetime(frame["recid_date"], errors="coerce").dt.normalize()
    frame["low_bac"] = pd.to_numeric(frame["low_score"], errors="coerce") / 1000
    frame["low_bac_bin"] = pd.to_numeric(frame["low_score_mod"], errors="coerce") / 1000
    frame["future_bac"] = pd.to_numeric(frame["recid_bac"], errors="coerce") / 1000
    frame["recidivism"] = pd.to_numeric(frame["recidivism"], errors="coerce").fillna(0).astype(int)
    frame["crime"] = pd.to_numeric(frame["crime"], errors="coerce")
    frame["offense"] = pd.to_numeric(frame["offense"], errors="coerce")
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["License"] = frame["License"].fillna("").astype(str)

    parsed = frame["SubjectName"].map(parse_breath_name)
    frame["subject_name_norm"] = [item.full_name_norm for item in parsed]
    frame["last_name_norm"] = [item.last_name_norm for item in parsed]
    frame["first_name_norm"] = [item.first_name_norm for item in parsed]
    frame["first_initial"] = [item.first_initial for item in parsed]
    frame["middle_initial"] = [item.middle_initial for item in parsed]
    frame["license_norm"] = frame["License"].str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)

    age = (frame["event_date"] - frame["dob_date"]).dt.days / 365.25
    frame["age_at_event"] = age
    frame = frame[
        frame["event_date"].notna()
        & frame["dob_date"].notna()
        & frame["crime"].eq(1)
        & frame["age_at_event"].ge(LEGAL_AGE)
        & frame["low_bac"].between(BAC_MIN, BAC_MAX, inclusive="both")
    ].copy()
    frame["event_id"] = np.arange(len(frame))
    return frame


def prepare_scatter_sample(sample: pd.DataFrame) -> pd.DataFrame:
    return sample[sample["year"].le(FOLLOWUP_COHORT_END_YEAR)].copy()


def summarize_panel_by_year(panel: pd.DataFrame, prefix: str) -> pd.DataFrame:
    summary = (
        panel.groupby("year", as_index=False)
        .agg(
            rows=("Date", "size"),
            mean_low_bac=("low_score", lambda s: pd.to_numeric(s, errors="coerce").mean() / 1000),
            recid_rate=("recidivism", lambda s: pd.to_numeric(s, errors="coerce").mean()),
        )
        .rename(
            columns={
                "rows": f"{prefix}_rows",
                "mean_low_bac": f"{prefix}_mean_low_bac",
                "recid_rate": f"{prefix}_recid_rate",
            }
        )
    )
    return summary


def compare_panels(saved: pd.DataFrame, rebuilt: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    overlap_years = sorted(set(saved["year"].dropna().astype(int)).intersection(set(rebuilt["year"].dropna().astype(int))))
    saved_overlap = saved[saved["year"].isin(overlap_years)].copy()
    rebuilt_overlap = rebuilt[rebuilt["year"].isin(overlap_years)].copy()

    by_year = summarize_panel_by_year(saved_overlap, "saved").merge(
        summarize_panel_by_year(rebuilt_overlap, "rebuilt"),
        on="year",
        how="outer",
    ).sort_values("year")
    by_year["row_diff_rebuilt_minus_saved"] = by_year["rebuilt_rows"].fillna(0) - by_year["saved_rows"].fillna(0)

    saved_keys = saved_overlap.assign(
        event_date=saved_overlap["Date"],
        dob_date=saved_overlap["dob"],
        subject_name_norm=saved_overlap["SubjectName"].map(lambda value: parse_breath_name(value).full_name_norm),
        low_score=pd.to_numeric(saved_overlap["low_score"], errors="coerce"),
    )[["event_date", "dob_date", "subject_name_norm", "low_score", "offense", "recidivism"]].drop_duplicates()

    rebuilt_keys = rebuilt_overlap.assign(
        event_date=rebuilt_overlap["Date"],
        dob_date=rebuilt_overlap["dob"],
        subject_name_norm=rebuilt_overlap["SubjectName"].map(lambda value: parse_breath_name(value).full_name_norm),
        low_score=pd.to_numeric(rebuilt_overlap["low_score"], errors="coerce"),
    )[["event_date", "dob_date", "subject_name_norm", "low_score", "offense", "recidivism"]].drop_duplicates()

    matched = saved_keys.merge(
        rebuilt_keys,
        on=["event_date", "dob_date", "subject_name_norm", "low_score"],
        how="outer",
        indicator=True,
        suffixes=("_saved", "_rebuilt"),
    )
    matched_both = matched[matched["_merge"] == "both"].copy()

    summary_rows = [
        {"metric": "overlap_year_start", "value": min(overlap_years)},
        {"metric": "overlap_year_end", "value": max(overlap_years)},
        {"metric": "saved_rows_overlap_years", "value": int(len(saved_overlap))},
        {"metric": "rebuilt_rows_overlap_years", "value": int(len(rebuilt_overlap))},
        {"metric": "saved_unique_events", "value": int(len(saved_keys))},
        {"metric": "rebuilt_unique_events", "value": int(len(rebuilt_keys))},
        {"metric": "matched_unique_events", "value": int(len(matched_both))},
        {"metric": "share_saved_events_recovered", "value": float(len(matched_both) / len(saved_keys))},
        {"metric": "share_rebuilt_events_in_saved", "value": float(len(matched_both) / len(rebuilt_keys))},
        {
            "metric": "matched_offense_agreement",
            "value": float((matched_both["offense_saved"] == matched_both["offense_rebuilt"]).mean()),
        },
        {
            "metric": "matched_recidivism_agreement",
            "value": float((matched_both["recidivism_saved"] == matched_both["recidivism_rebuilt"]).mean()),
        },
    ]
    return by_year, pd.DataFrame(summary_rows)


def append_plot_summary(summary: pd.DataFrame, sample: pd.DataFrame, prefix: str) -> pd.DataFrame:
    rows = []
    groups = {
        "overall": sample,
        "first_time": sample[sample["offense"].eq(1)],
        "repeat": sample[sample["offense"].ge(2)],
    }
    for group_name, group_frame in groups.items():
        rows.append({"metric": f"{prefix}_{group_name}_n", "value": int(len(group_frame))})
        rows.append({"metric": f"{prefix}_{group_name}_recid_rate", "value": float(group_frame["recidivism"].mean())})
    return pd.concat([summary, pd.DataFrame(rows)], ignore_index=True)


def write_outputs(
    rebuilt_panel: pd.DataFrame,
    source_summary: pd.DataFrame,
    compare_by_year: pd.DataFrame,
    compare_summary: pd.DataFrame,
    scatter_sample: pd.DataFrame,
    linked: pd.DataFrame,
    match_summary: pd.DataFrame,
    court_max_year: int,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rebuilt_panel.to_csv(OUT_PANEL, index=False, compression="gzip")
    source_summary.to_csv(OUT_SOURCE_SUMMARY, index=False)
    compare_by_year.to_csv(OUT_COMPARE_YEAR, index=False)
    compare_summary.to_csv(OUT_COMPARE_SUMMARY, index=False)

    binned = build_binned_summary(scatter_sample)
    binned.to_csv(OUT_BINNED, index=False)
    plot_scatter_panels(scatter_sample, binned)

    linked_out = linked[
        [
            "event_id",
            "event_date",
            "dob_date",
            "SubjectName",
            "low_bac",
            "offense",
            "year",
            "recidivism",
            "future_bac",
            "matched",
            "score",
            "match_quality",
            "date_diff",
            "dob_diff",
            "last_ratio",
            "first_ratio",
            "full_ratio",
            "license_exact",
            "offender_name",
            "court_code",
            "judge",
            "guilty",
            "amended",
            "dismissed",
            "deferred",
            "not_guilty",
            "fine",
            "jail",
            "probation",
            "license_susp",
            "victims_panel",
            "alcohol_assess",
            "alcohol_treatment",
            "aa",
        ]
    ].copy()
    linked_out.to_csv(OUT_LINKED, index=False)
    match_summary.to_csv(OUT_MATCH_SUMMARY, index=False)

    compare_map = compare_summary.set_index("metric")["value"].to_dict()
    match_rate = float(match_summary.loc[match_summary["metric"] == "match_rate", "value"].iloc[0] * 100)

    md = [
        "# Breath-test BAC, 3-year recidivism, and court linkage",
        "",
        "This package rebuilds the DUI analysis panel directly from `breath_test_10_2016.csv`, uses the yearly `alcohol_*` files as a raw-source coverage audit, compares the rebuilt panel against the saved `dui_analysis.dta`, and reruns the BAC scatter plus court linkage from the rebuilt panel.",
        "",
        "## Raw sources",
        "",
        f"- Primary rebuild source: `Older/{RAW_BREATH_CSV_PATH.name}`",
        "- Audit source: yearly `Older/alcohol_*.dta` files, including `alcohol_2014.dta` for 2012-2014",
        f"- Rebuilt analysis panel: `{OUT_PANEL.name}`",
        f"- Legacy-comparable scatter window kept at `{FOLLOWUP_COHORT_END_YEAR}` to match the original figure design",
        "",
        "## Saved-panel comparison",
        "",
        f"- Overlap years: `{int(compare_map['overlap_year_start'])}-{int(compare_map['overlap_year_end'])}`",
        f"- Share of saved events recovered: `{compare_map['share_saved_events_recovered'] * 100:.1f}%`",
        f"- Share of rebuilt events also in saved panel: `{compare_map['share_rebuilt_events_in_saved'] * 100:.1f}%`",
        f"- Offense agreement on matched events: `{compare_map['matched_offense_agreement'] * 100:.1f}%`",
        f"- Recidivism agreement on matched events: `{compare_map['matched_recidivism_agreement'] * 100:.1f}%`",
        f"- Saved plot sample: `N = {int(compare_map['saved_plot_overall_n']):,}`, 3-year future DUI = `{compare_map['saved_plot_overall_recid_rate'] * 100:.1f}%`",
        f"- Rebuilt plot sample: `N = {int(compare_map['rebuilt_plot_overall_n']):,}`, 3-year future DUI = `{compare_map['rebuilt_plot_overall_recid_rate'] * 100:.1f}%`",
        "- Year-by-year recidivism rates diverge after 2007 because the rebuilt raw panel has follow-up through 2016, while the saved panel ends in 2010 and is mechanically right-censored in its later years.",
        "",
        f"![BAC and future DUI]({OUT_FIG.name})",
        "",
        "## Court linkage",
        "",
        f"- Linkage sample restricted to breath-test years covered by the court file through `{court_max_year}`",
        f"- Match rate: `{match_rate:.1f}%`",
        "",
        "## Files",
        "",
        f"- [rebuilt_dui_analysis_panel.csv.gz]({OUT_PANEL.name})",
        f"- [rebuilt_breath_source_by_year.csv]({OUT_SOURCE_SUMMARY.name})",
        f"- [rebuilt_vs_saved_dui_panel_by_year.csv]({OUT_COMPARE_YEAR.name})",
        f"- [rebuilt_vs_saved_dui_panel_summary.csv]({OUT_COMPARE_SUMMARY.name})",
        f"- [bac_recidivism_three_panel.svg]({OUT_FIG.name})",
        f"- [bac_recidivism_binned.csv]({OUT_BINNED.name})",
        f"- [breath_to_court_linked_events.csv]({OUT_LINKED.name})",
        f"- [breath_to_court_match_summary.csv]({OUT_MATCH_SUMMARY.name})",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    rebuilt_panel = build_rebuilt_panel()
    saved_panel = load_saved_panel()
    rebuilt_sample = prepare_analysis_sample(rebuilt_panel)
    saved_sample = prepare_analysis_sample(saved_panel)

    source_summary = annual_raw_counts().merge(
        rebuilt_panel["year"].value_counts().sort_index().rename_axis("year").reset_index(name="rebuilt_panel_rows"),
        on="year",
        how="outer",
    )
    source_summary = source_summary.merge(
        pd.to_datetime(pd.read_csv(RAW_BREATH_CSV_PATH, usecols=["BreathTestDate"])["BreathTestDate"], errors="coerce")
        .dt.year.value_counts()
        .sort_index()
        .rename_axis("year")
        .reset_index(name="breath_test_raw_rows"),
        on="year",
        how="outer",
    )
    source_summary = source_summary.merge(
        saved_panel["year"].value_counts().sort_index().rename_axis("year").reset_index(name="saved_panel_rows"),
        on="year",
        how="outer",
    ).sort_values("year")
    source_summary[["annual_raw_rows", "rebuilt_panel_rows", "breath_test_raw_rows", "saved_panel_rows"]] = source_summary[
        ["annual_raw_rows", "rebuilt_panel_rows", "breath_test_raw_rows", "saved_panel_rows"]
    ].fillna(0).astype(int)

    compare_by_year, compare_summary = compare_panels(saved_panel, rebuilt_panel)
    compare_summary = append_plot_summary(compare_summary, prepare_scatter_sample(saved_sample), "saved_plot")
    compare_summary = append_plot_summary(compare_summary, prepare_scatter_sample(rebuilt_sample), "rebuilt_plot")

    court = prepare_court_panel()
    court_max_year = int(court["doa_date"].max().year)
    linkage_sample = rebuilt_sample[rebuilt_sample["year"].le(court_max_year)].copy()
    candidates = make_date_candidates(linkage_sample, court, offsets=tuple(range(-DATE_WINDOW_DAYS, DATE_WINDOW_DAYS + 1)), dob_shifts=(0, 365, 366, -365, -366))
    linked = pick_best_matches(linkage_sample, score_candidates(candidates))

    match_summary = pd.DataFrame(
        [
            {"metric": "linkage_sample_events", "value": int(len(linked))},
            {"metric": "matched_events", "value": int(linked["matched"].sum())},
            {"metric": "match_rate", "value": float(linked["matched"].mean())},
        ]
    )

    write_outputs(
        rebuilt_panel=rebuilt_panel,
        source_summary=source_summary,
        compare_by_year=compare_by_year,
        compare_summary=compare_summary,
        scatter_sample=prepare_scatter_sample(rebuilt_sample),
        linked=linked,
        match_summary=match_summary,
        court_max_year=court_max_year,
    )

    print(f"Wrote rebuilt panel to {OUT_PANEL}")
    print(f"Wrote source summary to {OUT_SOURCE_SUMMARY}")
    print(f"Wrote comparison by year to {OUT_COMPARE_YEAR}")
    print(f"Wrote comparison summary to {OUT_COMPARE_SUMMARY}")


if __name__ == "__main__":
    main()
