from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from breath_bac_recidivism_linkage import normalize_text, parse_breath_name
from rebuild_breath_bac_panel import (
    BAD_SUBJECT_NAMES,
    build_person_id_key,
    build_rebuilt_panel,
    compare_panels,
    split_subject_name,
)


ROOT = Path(__file__).resolve().parents[3]
DATAMASTER_PATH = ROOT / "2019" / "R002834-030519_Datamaster_DB_1995-2019_-_Redacted.xlsx"
DRAEGER_PATH = ROOT / "2019" / "R002834-030519_Draeger_DB_1995-2019_-_Redacted.xlsx"
OUT_DIR = ROOT / "breath_panel_2019_rebuild"
OUT_RAW = OUT_DIR / "standardized_breath_raw_1995_2019.parquet"
OUT_PANEL_PARQUET = OUT_DIR / "breath_panel_1995_2019.parquet"
OUT_PANEL_CSV = OUT_DIR / "breath_panel_1995_2019.csv.gz"
OUT_SOURCE_YEARS = OUT_DIR / "breath_panel_1995_2019_source_years.csv"
OUT_NAME_COVERAGE = OUT_DIR / "breath_panel_1995_2019_name_coverage.csv"
OUT_COMPARE_YEAR = OUT_DIR / "breath_panel_1995_2019_vs_rebuilt2016_by_year.csv"
OUT_COMPARE_SUMMARY = OUT_DIR / "breath_panel_1995_2019_vs_rebuilt2016_summary.csv"
OUT_MD = OUT_DIR / "breath_panel_1995_2019_rebuild.md"

MIN_ANALYSIS_DATE = pd.Timestamp("1995-01-01")


def build_operator_name(last: pd.Series, first: pd.Series, middle: pd.Series) -> pd.Series:
    last_s = last.fillna("").astype(str).str.strip().str.upper()
    first_s = first.fillna("").astype(str).str.strip().str.upper()
    middle_s = middle.fillna("").astype(str).str.strip().str.upper()
    full = last_s
    full = np.where(first_s.ne(""), full + "/" + first_s, full)
    full = np.where(middle_s.ne(""), full + "/" + middle_s, full)
    return pd.Series(full, index=last.index)


def standardize_time_value(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""

    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.strftime("%H:%M:%S")

    match = pd.Series([text]).str.extract(r"(\d{1,2}:\d{2}(?::\d{2})?)", expand=False).iloc[0]
    if isinstance(match, str) and match:
        parts = match.split(":")
        if len(parts) == 2:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
        if len(parts) == 3:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    return text


def standardize_time_series(series: pd.Series) -> pd.Series:
    return series.map(standardize_time_value)


def first_nonempty(values: pd.Series) -> str:
    nonempty = values.fillna("").astype(str)
    nonempty = nonempty[nonempty.ne("")]
    if nonempty.empty:
        return ""
    return nonempty.iloc[0]


def time_to_seconds(value: object) -> float:
    text = standardize_time_value(value)
    if not text:
        return np.nan
    parts = text.split(":")
    if len(parts) != 3:
        return np.nan
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        return np.nan
    return float(hours * 3600 + minutes * 60 + seconds)


def read_datamaster() -> pd.DataFrame:
    cols = [
        "SerialNo",
        "Date",
        "Time",
        "Obs Time",
        "Citation",
        "Operator",
        "Agency",
        "SubjectName",
        "DOB",
        "Sex",
        "EthnicGroup",
        "License",
        "County",
        "crime",
        "Accident",
        "Location",
        "PBTResult",
        "Alcohol1char",
        "Alcohol1",
        "Alcohol2char",
        "Alcohol2",
        "PBTTime",
        "Time of Alc1",
        "Time of Alc2",
    ]
    frame = pd.read_excel(DATAMASTER_PATH, usecols=cols)
    frame = frame.rename(
        columns={
            "Date": "event_date",
            "Citation": "citation",
            "Operator": "operator",
            "Agency": "agency",
            "SubjectName": "subject_name",
            "DOB": "dob",
            "Sex": "sex",
            "EthnicGroup": "ethnic_group",
            "License": "license",
            "County": "county",
            "crime": "crime",
            "Accident": "accident",
            "Location": "location",
            "PBTResult": "pbt_result",
            "Alcohol1char": "alcohol1char",
            "Alcohol1": "alcohol1",
            "Alcohol2char": "alcohol2char",
            "Alcohol2": "alcohol2",
            "SerialNo": "serial_no",
            "Time": "event_time",
            "Obs Time": "observation_start_time",
            "PBTTime": "pbt_time",
            "Time of Alc1": "test1_blow_time",
            "Time of Alc2": "test2_blow_time",
        }
    )
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.normalize()
    frame["dob"] = pd.to_datetime(frame["dob"], errors="coerce").dt.normalize()
    frame["serial_no"] = frame["serial_no"].fillna("").astype(str)
    frame["citation"] = frame["citation"].fillna("").astype(str)
    frame["operator"] = frame["operator"].fillna("").astype(str)
    frame["agency"] = frame["agency"].fillna("").astype(str)
    frame["subject_name"] = frame["subject_name"].fillna("").astype(str)
    frame["sex"] = frame["sex"].fillna("").astype(str).str.upper().str[:1]
    frame["ethnic_group"] = frame["ethnic_group"].fillna("").astype(str).str.upper().str[:1]
    frame["license"] = frame["license"].fillna("").astype(str)
    frame["county"] = pd.to_numeric(frame["county"], errors="coerce")
    frame["crime"] = pd.to_numeric(frame["crime"], errors="coerce")
    frame["accident"] = frame["accident"].fillna("").astype(str).str.upper().str[:1]
    frame["location"] = frame["location"].fillna("").astype(str)
    frame["pbt_result"] = pd.to_numeric(frame["pbt_result"], errors="coerce")
    frame["alcohol1"] = pd.to_numeric(frame["alcohol1"], errors="coerce").round()
    frame["alcohol2"] = pd.to_numeric(frame["alcohol2"], errors="coerce").round()
    frame["event_time"] = standardize_time_series(frame["event_time"])
    frame["observation_start_time"] = standardize_time_series(frame["observation_start_time"])
    frame["pbt_time"] = standardize_time_series(frame["pbt_time"])
    frame["test1_blow_time"] = standardize_time_series(frame["test1_blow_time"])
    frame["test2_blow_time"] = standardize_time_series(frame["test2_blow_time"])
    frame["test1_end_time"] = ""
    frame["test2_end_time"] = ""
    frame["source"] = "datamaster"
    return frame[
        [
            "source",
            "serial_no",
            "event_date",
            "event_time",
            "observation_start_time",
            "pbt_time",
            "test1_blow_time",
            "test1_end_time",
            "test2_blow_time",
            "test2_end_time",
            "citation",
            "operator",
            "agency",
            "subject_name",
            "dob",
            "sex",
            "ethnic_group",
            "license",
            "county",
            "crime",
            "accident",
            "location",
            "pbt_result",
            "alcohol1char",
            "alcohol1",
            "alcohol2char",
            "alcohol2",
        ]
    ].copy()


def read_draeger() -> pd.DataFrame:
    cols = [
        "SerialNo",
        "StartTime",
        "ObservationStartTime",
        "PBTTime",
        "CitationCaseNumber",
        "OperatorLastName",
        "OperatorFirstName",
        "OperatorMiddleInitial",
        "OperatorAgencyCode",
        "SubjectLastName",
        "SubjectFirstName",
        "SubjectMiddleInitial",
        "SubjectDateOfBirth",
        "SubjectGender",
        "SubjectEthnicGroup",
        "SubjectDriverLicenseNumber",
        "CountyOfArrest",
        "CrimeArrestedFor",
        "CollisionInvolved",
        "SelectAppropriateDrinkingLocation",
        "PBTResult",
        "Prob1IrBracResult",
        "Prob1BlowTime",
        "Prob2IrBracResult",
        "Prob2BlowTime",
        "IDTimeStartBlow1",
        "IDTimeEndBlow1",
        "IDTimeStartBlow3",
        "IDTimeEndBlow3",
    ]
    frame = pd.read_excel(DRAEGER_PATH, usecols=cols)
    subject_name = build_operator_name(frame["SubjectLastName"], frame["SubjectFirstName"], frame["SubjectMiddleInitial"])
    operator_name = build_operator_name(frame["OperatorLastName"], frame["OperatorFirstName"], frame["OperatorMiddleInitial"])
    frame = pd.DataFrame(
        {
            "source": "draeger",
            "serial_no": frame["SerialNo"].fillna("").astype(str),
            "event_date": pd.to_datetime(frame["StartTime"], errors="coerce").dt.normalize(),
            "event_time": standardize_time_series(frame["StartTime"]),
            "observation_start_time": standardize_time_series(frame["ObservationStartTime"]),
            "pbt_time": standardize_time_series(frame["PBTTime"]),
            "test1_blow_time": standardize_time_series(frame["Prob1BlowTime"].where(frame["Prob1BlowTime"].notna(), frame["IDTimeStartBlow1"])),
            "test1_end_time": standardize_time_series(frame["IDTimeEndBlow1"]),
            "test2_blow_time": standardize_time_series(frame["Prob2BlowTime"].where(frame["Prob2BlowTime"].notna(), frame["IDTimeStartBlow3"])),
            "test2_end_time": standardize_time_series(frame["IDTimeEndBlow3"]),
            "citation": frame["CitationCaseNumber"].fillna("").astype(str),
            "operator": operator_name.fillna("").astype(str),
            "agency": frame["OperatorAgencyCode"].fillna("").astype(str),
            "subject_name": subject_name.fillna("").astype(str),
            "dob": pd.to_datetime(frame["SubjectDateOfBirth"], errors="coerce").dt.normalize(),
            "sex": frame["SubjectGender"].fillna("").astype(str).str.upper().str[:1],
            "ethnic_group": frame["SubjectEthnicGroup"].fillna("").astype(str).str.upper().str[:1],
            "license": frame["SubjectDriverLicenseNumber"].fillna("").astype(str),
            "county": pd.to_numeric(frame["CountyOfArrest"], errors="coerce"),
            "crime": pd.to_numeric(frame["CrimeArrestedFor"], errors="coerce"),
            "accident": frame["CollisionInvolved"].fillna("").astype(str).str.upper().str[:1],
            "location": frame["SelectAppropriateDrinkingLocation"].fillna("").astype(str),
            "pbt_result": pd.to_numeric(frame["PBTResult"], errors="coerce"),
            "alcohol1char": "",
            "alcohol1": pd.to_numeric(frame["Prob1IrBracResult"], errors="coerce").mul(1000).round(),
            "alcohol2char": "",
            "alcohol2": pd.to_numeric(frame["Prob2IrBracResult"], errors="coerce").mul(1000).round(),
        }
    )
    return frame


def summarize_name_coverage(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["age_at_event"] = (frame["event_date"] - frame["dob"]).dt.days / 365.25
    frame["has_real_name"] = ~frame["subject_name"].map(normalize_text).str.contains("CODE", na=False)

    bands = [
        ("under18", frame["age_at_event"] < 18),
        ("18to20", frame["age_at_event"].between(18, 21, inclusive="left")),
        ("21plus", frame["age_at_event"] >= 21),
    ]
    rows: list[dict[str, object]] = []
    for source, sub in frame.groupby("source"):
        for age_group, mask in bands:
            part = sub[mask.loc[sub.index]].copy()
            if part.empty:
                continue
            rows.append(
                {
                    "source": source,
                    "age_group": age_group,
                    "rows": int(len(part)),
                    "real_name_share": float(part["has_real_name"].mean()),
                }
            )
    return pd.DataFrame(rows)


def clean_and_panelize(raw: pd.DataFrame) -> pd.DataFrame:
    panel = raw.copy()
    panel["subject_name_clean"] = panel["subject_name"].map(normalize_text)
    panel["operator_clean"] = panel["operator"].map(normalize_text)

    panel = panel[
        panel["event_date"].notna()
        & panel["dob"].notna()
        & panel["crime"].notna()
        & panel["subject_name_clean"].ne("")
        & ~panel["subject_name_clean"].isin(BAD_SUBJECT_NAMES)
        & ~panel["subject_name_clean"].str.contains("CODE", na=False)
        & ~panel["subject_name_clean"].eq(panel["operator_clean"])
    ].copy()

    parts = panel["subject_name"].map(split_subject_name)
    name_parts = pd.DataFrame(parts.tolist(), index=panel.index, columns=["SubjectName1", "SubjectName2", "SubjectName3", "SubjectName4"])
    panel = pd.concat([panel, name_parts], axis=1)
    panel = panel[~panel["SubjectName1"].isin(["TEST", "NEW", "CODE"])].copy()
    panel["SubjectName2"] = np.where(panel["SubjectName2"].eq(""), panel["SubjectName3"], panel["SubjectName2"])
    panel["SubjectName3"] = np.where(panel["SubjectName3"].eq(""), panel["SubjectName4"], panel["SubjectName3"])
    panel["SubjectName2"] = panel["SubjectName2"].where(panel["SubjectName2"].ne(""), "A")
    panel["middle"] = panel["SubjectName3"].str[:1]
    panel["middle"] = panel["middle"].where(panel["middle"].ne(""), "A")
    panel["license"] = np.where(panel["license"].astype(str).str.contains("Code", case=False, na=False), "", panel["license"])

    panel = panel.drop_duplicates().copy()
    panel["id_key"] = build_person_id_key(
        panel["SubjectName1"],
        panel["SubjectName2"],
        panel["dob"],
        panel["sex"],
    )
    panel["id"] = pd.factorize(panel["id_key"], sort=False)[0] + 1

    panel.loc[(panel["alcohol1"] > 0) & panel["alcohol2"].fillna(0).eq(0), "alcohol2"] = np.nan
    panel.loc[(panel["alcohol1"].fillna(0).eq(0)) & (panel["alcohol2"] > 0), "alcohol2"] = np.nan
    panel["pair_diff_abs"] = (panel["alcohol1"] - panel["alcohol2"]).abs()
    panel["has_two_numeric_tests"] = panel["alcohol1"].notna() & panel["alcohol2"].notna()
    panel["pair_gap_gt_20"] = (panel["has_two_numeric_tests"] & panel["pair_diff_abs"].gt(20)).astype(int)
    panel["pair_gap_le_20"] = (panel["has_two_numeric_tests"] & panel["pair_diff_abs"].le(20)).astype(int)
    panel["row_low_score"] = panel[["alcohol1", "alcohol2"]].min(axis=1, skipna=True)
    panel["event_time_seconds"] = panel["event_time"].map(time_to_seconds)
    panel["observation_start_seconds"] = panel.get("observation_start_time", "").map(time_to_seconds) if "observation_start_time" in panel.columns else np.nan
    panel["test1_blow_seconds"] = panel.get("test1_blow_time", "").map(time_to_seconds) if "test1_blow_time" in panel.columns else np.nan
    panel["test2_blow_seconds"] = panel.get("test2_blow_time", "").map(time_to_seconds) if "test2_blow_time" in panel.columns else np.nan
    panel["row_sort_seconds"] = panel[["test2_blow_seconds", "test1_blow_seconds", "event_time_seconds", "observation_start_seconds"]].max(axis=1, skipna=True)
    panel["row_sort_seconds"] = panel["row_sort_seconds"].fillna(-1)

    same_day = panel.groupby(["id", "event_date"], sort=False)
    panel["same_day_row_count"] = same_day["id"].transform("size")
    panel["has_same_day_retest_line"] = panel["same_day_row_count"].gt(1).astype(int)
    panel["any_same_day_pair_gap_gt_20"] = same_day["pair_gap_gt_20"].transform("max")
    panel["any_same_day_admissible_pair"] = same_day["pair_gap_le_20"].transform("max")
    panel["same_day_legacy_low_score"] = same_day["row_low_score"].transform("min")
    panel["same_day_latest_seconds"] = same_day["row_sort_seconds"].transform("max")
    panel["latest_same_day_row"] = (
        panel["row_sort_seconds"].eq(panel["same_day_latest_seconds"])
        & same_day.cumcount(ascending=False).eq(0)
    ).astype(int)
    admissible_rows = panel.loc[panel["pair_gap_le_20"].eq(1)].copy()
    if not admissible_rows.empty:
        admissible_rows["latest_admissible_same_day_row"] = (
            admissible_rows["row_sort_seconds"].eq(
                admissible_rows.groupby(["id", "event_date"], sort=False)["row_sort_seconds"].transform("max")
            )
            & admissible_rows.groupby(["id", "event_date"], sort=False).cumcount(ascending=False).eq(0)
        ).astype(int)
        admissible_latest = (
            admissible_rows.loc[admissible_rows["latest_admissible_same_day_row"].eq(1), ["id", "event_date", "alcohol1", "alcohol2", "row_low_score"]]
            .rename(
                columns={
                    "alcohol1": "admissible_alcohol1",
                    "alcohol2": "admissible_alcohol2",
                    "row_low_score": "low_score_admissible",
                }
            )
            .copy()
        )
        panel = panel.merge(admissible_latest, on=["id", "event_date"], how="left")
    else:
        panel["admissible_alcohol1"] = np.nan
        panel["admissible_alcohol2"] = np.nan
        panel["low_score_admissible"] = np.nan

    for time_col in [
        "event_time",
        "observation_start_time",
        "pbt_time",
        "test1_blow_time",
        "test1_end_time",
        "test2_blow_time",
        "test2_end_time",
    ]:
        panel[time_col] = same_day[time_col].transform(first_nonempty)
    panel = (
        panel.sort_values(
            ["id", "event_date", "any_same_day_admissible_pair", "pair_gap_le_20", "row_sort_seconds", "source", "serial_no", "citation"],
            ascending=[True, True, False, False, False, True, True, True],
        )
        .drop_duplicates(["id", "event_date"], keep="first")
        .copy()
    )

    panel["offense"] = panel.groupby("id").cumcount() + 1
    panel["total_dui"] = panel.groupby("id")["offense"].transform("max") - 1
    panel["Alcohol1_legacy"] = panel["same_day_legacy_low_score"]
    panel["low_score_legacy"] = panel["same_day_legacy_low_score"]
    panel["selected_row_pair_gap_gt_20"] = panel["pair_gap_gt_20"]
    panel["selected_row_pair_gap_le_20"] = panel["pair_gap_le_20"]
    panel["selected_row_is_latest_same_day"] = panel["latest_same_day_row"]
    panel["selected_row_has_two_numeric_tests"] = panel["has_two_numeric_tests"].astype(int)
    panel["selected_row_low_score"] = panel["row_low_score"]
    panel["low_score"] = np.where(panel["low_score_admissible"].notna(), panel["low_score_admissible"], panel["same_day_legacy_low_score"])
    panel["admissibility_retest_used"] = (
        panel["has_same_day_retest_line"].eq(1)
        & panel["any_same_day_pair_gap_gt_20"].eq(1)
        & panel["any_same_day_admissible_pair"].eq(1)
    ).astype(int)
    panel = panel[panel["event_date"] >= MIN_ANALYSIS_DATE].copy()
    panel["low_score_mod"] = np.where(panel["low_score"].notna(), panel["low_score"] - np.mod(panel["low_score"], 2), np.nan)
    panel["year"] = panel["event_date"].dt.year
    panel["male"] = panel["sex"].astype(str).str.upper().eq("M").astype(int)
    panel["white"] = panel["ethnic_group"].astype(str).str.upper().eq("W").astype(int)

    panel["acc_fut"] = panel.groupby("id")["accident"].shift(-1).fillna("")
    panel["recid_date"] = panel.groupby("id")["event_date"].shift(-1)
    panel["recid_bac"] = panel.groupby("id")["low_score"].shift(-1)
    panel["refusal1"] = ""
    panel["refusal2"] = ""
    days_to_next = (panel["recid_date"] - panel["event_date"]).dt.days
    panel["recidivism"] = ((days_to_next <= 1462) & (days_to_next > 0)).astype(int)
    panel["acc_recid"] = ((panel["recidivism"] == 1) & panel["acc_fut"].astype(str).str.upper().eq("Y")).astype(int)
    panel["diff"] = panel["alcohol1"] - panel["alcohol2"]

    panel = panel.rename(
        columns={
            "event_date": "Date",
            "citation": "Citation",
            "operator": "Operator",
            "agency": "Agency",
            "subject_name": "SubjectName",
            "sex": "Sex",
            "ethnic_group": "EthnicGroup",
            "county": "County",
            "crime": "crime",
            "accident": "Accident",
            "location": "Location",
            "alcohol1char": "Alcohol1char",
            "alcohol1": "Alcohol1",
            "alcohol2char": "Alcohol2char",
            "alcohol2": "Alcohol2",
            "serial_no": "SerialNo",
            "license": "License",
        }
    )
    return panel[
        [
            "source",
            "SerialNo",
            "Date",
            "event_time",
            "observation_start_time",
            "pbt_time",
            "test1_blow_time",
            "test1_end_time",
            "test2_blow_time",
            "test2_end_time",
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
            "low_score_legacy",
            "low_score_admissible",
            "admissible_alcohol1",
            "admissible_alcohol2",
            "low_score_mod",
            "pair_diff_abs",
            "pair_gap_gt_20",
            "pair_gap_le_20",
            "same_day_row_count",
            "has_same_day_retest_line",
            "any_same_day_pair_gap_gt_20",
            "any_same_day_admissible_pair",
            "admissibility_retest_used",
            "selected_row_pair_gap_gt_20",
            "selected_row_pair_gap_le_20",
            "selected_row_has_two_numeric_tests",
            "selected_row_is_latest_same_day",
            "selected_row_low_score",
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


def summarize_sources(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (source, year), count in raw.groupby(["source", raw["event_date"].dt.year]).size().items():
        rows.append({"source": source, "year": int(year), "rows": int(count)})
    return pd.DataFrame(rows).sort_values(["source", "year"]).reset_index(drop=True)


def compare_with_rebuilt2016(panel_2019: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    old_panel = build_rebuilt_panel()
    comparable_new = panel_2019[
        panel_2019["Date"].notna()
        & pd.to_numeric(panel_2019["low_score"], errors="coerce").notna()
        & pd.to_numeric(panel_2019["crime"], errors="coerce").eq(1)
    ].copy()
    old_compare, old_summary = compare_panels(old_panel, comparable_new)

    old_compare = old_compare.rename(
        columns={
            "saved_rows": "rebuilt2016_rows",
            "saved_mean_low_bac": "rebuilt2016_mean_low_bac",
            "saved_recid_rate": "rebuilt2016_recid_rate",
            "rebuilt_rows": "rebuilt2019_rows",
            "rebuilt_mean_low_bac": "rebuilt2019_mean_low_bac",
            "rebuilt_recid_rate": "rebuilt2019_recid_rate",
            "row_diff_rebuilt_minus_saved": "row_diff_2019_minus_2016",
        }
    )

    metric_map = {
        "saved_rows_overlap_years": "rebuilt2016_rows_overlap_years",
        "rebuilt_rows_overlap_years": "rebuilt2019_rows_overlap_years",
        "saved_unique_events": "rebuilt2016_unique_events",
        "rebuilt_unique_events": "rebuilt2019_unique_events",
        "share_saved_events_recovered": "share_rebuilt2016_events_found_in_2019",
        "share_rebuilt_events_in_saved": "share_rebuilt2019_events_found_in_2016",
        "matched_offense_agreement": "matched_offense_agreement",
        "matched_recidivism_agreement": "matched_recidivism_agreement",
    }
    old_summary["metric"] = old_summary["metric"].replace(metric_map)
    return old_compare, old_summary


def write_markdown(name_coverage: pd.DataFrame, compare_summary: pd.DataFrame, compare_by_year: pd.DataFrame, panel: pd.DataFrame) -> None:
    cover = name_coverage.set_index(["source", "age_group"])["real_name_share"].to_dict()
    compare = compare_summary.set_index("metric")["value"].to_dict()
    min_date = panel["Date"].min().date().isoformat()
    max_date = panel["Date"].max().date().isoformat()
    max_recid = panel["recid_date"].max().date().isoformat()

    md = [
        "# Breath panel rebuild through 2019",
        "",
        "This package rebuilds the person-level breath-test panel directly from the raw `2019` Datamaster and Draeger Excel extracts, then compares the rebuilt overlap years against the prior panel rebuilt from `breath_test_10_2016.csv`.",
        "",
        "## Coverage",
        "",
        f"- Rebuilt event dates run from `{min_date}` to `{max_date}`.",
        f"- Next-event follow-up in the rebuilt panel runs through `{max_recid}`.",
        f"- Adult real-name coverage in raw Datamaster: `{cover.get(('datamaster', '21plus'), np.nan) * 100:.2f}%`.",
        f"- Adult real-name coverage in raw Draeger: `{cover.get(('draeger', '21plus'), np.nan) * 100:.2f}%`.",
        f"- Age `18-20` real-name coverage in raw Datamaster: `{cover.get(('datamaster', '18to20'), np.nan) * 100:.2f}%`.",
        f"- Age `18-20` real-name coverage in raw Draeger: `{cover.get(('draeger', '18to20'), np.nan) * 100:.2f}%`.",
        f"- Under-18 real-name coverage is effectively zero in both raw sources, so the new youth sample should be interpreted as the `18-20` population rather than all minors.",
        "",
        "## Comparison to the prior rebuilt 2016 panel",
        "",
        f"- Overlap years: `{int(compare['overlap_year_start'])}-{int(compare['overlap_year_end'])}`.",
        f"- Share of 2016-based rebuilt unique events found in the 2019 raw rebuild: `{compare['share_rebuilt2016_events_found_in_2019'] * 100:.2f}%`.",
        f"- Share of 2019 raw rebuild unique events found in the 2016-based rebuild: `{compare['share_rebuilt2019_events_found_in_2016'] * 100:.2f}%`.",
        f"- Offense-order agreement on matched overlap events: `{compare['matched_offense_agreement'] * 100:.2f}%`.",
        f"- Recidivism agreement on matched overlap events: `{compare['matched_recidivism_agreement'] * 100:.2f}%`.",
        "",
        "## Files",
        "",
        f"- [breath_panel_1995_2019.parquet]({OUT_PANEL_PARQUET.name})",
        f"- [breath_panel_1995_2019.csv.gz]({OUT_PANEL_CSV.name})",
        f"- [breath_panel_1995_2019_source_years.csv]({OUT_SOURCE_YEARS.name})",
        f"- [breath_panel_1995_2019_name_coverage.csv]({OUT_NAME_COVERAGE.name})",
        f"- [breath_panel_1995_2019_vs_rebuilt2016_by_year.csv]({OUT_COMPARE_YEAR.name})",
        f"- [breath_panel_1995_2019_vs_rebuilt2016_summary.csv]({OUT_COMPARE_SUMMARY.name})",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    datamaster = read_datamaster()
    draeger = read_draeger()
    raw = pd.concat([datamaster, draeger], ignore_index=True)
    raw.to_parquet(OUT_RAW, index=False)

    name_coverage = summarize_name_coverage(raw)
    source_years = summarize_sources(raw)

    panel = clean_and_panelize(raw)
    panel.to_parquet(OUT_PANEL_PARQUET, index=False)
    panel.to_csv(OUT_PANEL_CSV, index=False, compression="gzip")

    compare_by_year, compare_summary = compare_with_rebuilt2016(panel)

    name_coverage.to_csv(OUT_NAME_COVERAGE, index=False)
    source_years.to_csv(OUT_SOURCE_YEARS, index=False)
    compare_by_year.to_csv(OUT_COMPARE_YEAR, index=False)
    compare_summary.to_csv(OUT_COMPARE_SUMMARY, index=False)
    write_markdown(name_coverage, compare_summary, compare_by_year, panel)

    print(f"Wrote rebuild package to {OUT_DIR}")


if __name__ == "__main__":
    main()
