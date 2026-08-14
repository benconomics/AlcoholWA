from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "2026" / "code" / "analysis"))

from rebuild_breath_bac_panel import BAD_SUBJECT_NAMES  # noqa: E402


OLD_RAW_PATH = ROOT / "breath_panel_2019_rebuild" / "standardized_breath_raw_1995_2019.parquet"
NEW_XLSX_PATH = ROOT / "2026" / "breathtests" / "R006001-040926_DB_REDACTED.xlsx"

OUT_DIR = ROOT / "breath_panel_2026_update"
TABLE_DIR = OUT_DIR / "tables"
FIG_DIR = OUT_DIR / "figures"
PRIVATE_DIR = OUT_DIR / "private"
OUT_RAW = OUT_DIR / "standardized_breath_raw_1995_2026_dedup.parquet"
OUT_PANEL_PARQUET = OUT_DIR / "breath_panel_1995_2026.parquet"
OUT_PANEL_CSV = OUT_DIR / "breath_panel_1995_2026.csv.gz"
STATA_INPUT_DIR = OUT_DIR / "stata_inputs"
STATA_RD_INPUT = STATA_INPUT_DIR / "breath_panel_rd_input.dta"
OUT_MD = OUT_DIR / "breath_panel_2026_update.md"

FOLLOWUP_DAYS = 1462
ADULT_MIN_BAC = 0.03
YOUTH_MIN_BAC = 0.0
MAX_BAC = 0.20

STANDARD_RAW_COLUMNS = [
    "source",
    "source_extract",
    "source_record_id",
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

PLOT_BLUE = "#1f4e79"
PLOT_GOLD = "#b7791f"
PLOT_TEXT = "#222222"


@dataclass
class ParsedName:
    last: str
    first: str
    middle: str

    @property
    def first_initial(self) -> str:
        return self.first[:1]

    @property
    def middle_initial(self) -> str:
        return self.middle[:1]


def normalize_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().strip()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_name_token(value: object) -> str:
    return re.sub(r"[^A-Z]", "", normalize_text(value))


def normalize_license(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(value))


def normalize_key_part(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return normalize_text(value)


def parse_subject_name(value: object) -> ParsedName:
    raw = "" if pd.isna(value) else str(value).strip()
    raw = raw.replace(",", "/")
    parts = [normalize_name_token(part) for part in raw.split("/") if normalize_name_token(part)]
    last = parts[0] if parts else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = parts[2] if len(parts) > 2 else ""
    return ParsedName(last=last, first=first, middle=middle)


def build_name(last: pd.Series, first: pd.Series, middle: pd.Series) -> pd.Series:
    last_s = last.fillna("").astype(str).str.strip().str.upper()
    first_s = first.fillna("").astype(str).str.strip().str.upper()
    middle_s = middle.fillna("").astype(str).str.strip().str.upper()
    full = last_s
    full = np.where(first_s.ne(""), full + "/" + first_s, full)
    full = np.where(middle_s.ne(""), full + "/" + middle_s.str[:1], full)
    return pd.Series(full, index=last.index)


def standardize_time_value_fast(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%H:%M:%S")
    text = str(value).strip()
    if not text or text.lower() == "nan" or text == ":":
        return ""
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3) or 0)
        if 0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.strftime("%H:%M:%S")
    return ""


def standardize_time_series_fast(series: pd.Series) -> pd.Series:
    return series.map(standardize_time_value_fast)


def time_to_seconds(value: object) -> float:
    text = standardize_time_value_fast(value)
    if not text:
        return np.nan
    hours, minutes, seconds = text.split(":")
    return float(int(hours) * 3600 + int(minutes) * 60 + int(seconds))


def add_missing_standard_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for col in STANDARD_RAW_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    return out[STANDARD_RAW_COLUMNS].copy()


def read_old_standardized_raw() -> pd.DataFrame:
    frame = pd.read_parquet(OLD_RAW_PATH)
    frame["source_extract"] = "2019_archive"
    frame["source_record_id"] = ""
    return add_missing_standard_columns(frame)


def read_new_datamaster() -> pd.DataFrame:
    cols = [
        "SerialNo",
        "BACDatamasterID",
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
        "PBTTime",
        "PBTResult",
        "Alcohol1char",
        "Alcohol1",
        "Alcohol2char",
        "Alcohol2",
        "Time of Alc1",
        "Time of Alc2",
    ]
    frame = pd.read_excel(NEW_XLSX_PATH, sheet_name="DataMaster", usecols=cols)
    out = pd.DataFrame(
        {
            "source": "datamaster",
            "source_extract": "2026_drop",
            "source_record_id": frame["BACDatamasterID"].fillna("").astype(str),
            "serial_no": frame["SerialNo"].fillna("").astype(str),
            "event_date": pd.to_datetime(frame["Date"], errors="coerce").dt.normalize(),
            "event_time": standardize_time_series_fast(frame["Time"]),
            "observation_start_time": standardize_time_series_fast(frame["Obs Time"]),
            "pbt_time": standardize_time_series_fast(frame["PBTTime"]),
            "test1_blow_time": standardize_time_series_fast(frame["Time of Alc1"]),
            "test1_end_time": "",
            "test2_blow_time": standardize_time_series_fast(frame["Time of Alc2"]),
            "test2_end_time": "",
            "citation": frame["Citation"].fillna("").astype(str),
            "operator": frame["Operator"].fillna("").astype(str),
            "agency": frame["Agency"].fillna("").astype(str),
            "subject_name": frame["SubjectName"].fillna("").astype(str),
            "dob": pd.to_datetime(frame["DOB"], errors="coerce").dt.normalize(),
            "sex": frame["Sex"].fillna("").astype(str).str.upper().str[:1],
            "ethnic_group": frame["EthnicGroup"].fillna("").astype(str).str.upper().str[:1],
            "license": frame["License"].fillna("").astype(str),
            "county": pd.to_numeric(frame["County"], errors="coerce"),
            "crime": pd.to_numeric(frame["crime"], errors="coerce"),
            "accident": frame["Accident"].fillna("").astype(str).str.upper().str[:1],
            "location": frame["Location"].fillna("").astype(str),
            "pbt_result": pd.to_numeric(frame["PBTResult"], errors="coerce"),
            "alcohol1char": frame["Alcohol1char"].fillna("").astype(str),
            "alcohol1": pd.to_numeric(frame["Alcohol1"], errors="coerce").round(),
            "alcohol2char": frame["Alcohol2char"].fillna("").astype(str),
            "alcohol2": pd.to_numeric(frame["Alcohol2"], errors="coerce").round(),
        }
    )
    return add_missing_standard_columns(out)


def read_new_draeger() -> pd.DataFrame:
    cols = [
        "SerialNo",
        "BreathTestID",
        "Date",
        "Obs Time",
        "PBT Time",
        "PBT Result",
        "Citation#",
        "Co",
        "Cr",
        "Acc",
        "Drnk Loc",
        "OperatorName",
        "Agency",
        "SubjectLastName",
        "SubjectFirstName",
        "SubjectMI",
        "SubjDOB",
        "Race",
        "Gender",
        "BrAC1 IR",
        "BrAC1 EC",
        "B1 Tm",
        "BrAC2 IR",
        "BrAC2 EC",
        "B2 Tm",
    ]
    frame = pd.read_excel(NEW_XLSX_PATH, sheet_name="DraegerBT", usecols=cols)
    subject_name = build_name(frame["SubjectLastName"], frame["SubjectFirstName"], frame["SubjectMI"])
    out = pd.DataFrame(
        {
            "source": "draeger",
            "source_extract": "2026_drop",
            "source_record_id": frame["BreathTestID"].fillna("").astype(str),
            "serial_no": frame["SerialNo"].fillna("").astype(str),
            "event_date": pd.to_datetime(frame["Date"], errors="coerce").dt.normalize(),
            "event_time": standardize_time_series_fast(frame["Date"]),
            "observation_start_time": standardize_time_series_fast(frame["Obs Time"]),
            "pbt_time": standardize_time_series_fast(frame["PBT Time"]),
            "test1_blow_time": standardize_time_series_fast(frame["B1 Tm"]),
            "test1_end_time": "",
            "test2_blow_time": standardize_time_series_fast(frame["B2 Tm"]),
            "test2_end_time": "",
            "citation": frame["Citation#"].fillna("").astype(str),
            "operator": frame["OperatorName"].fillna("").astype(str),
            "agency": frame["Agency"].fillna("").astype(str),
            "subject_name": subject_name.fillna("").astype(str),
            "dob": pd.to_datetime(frame["SubjDOB"], errors="coerce").dt.normalize(),
            "sex": frame["Gender"].fillna("").astype(str).str.upper().str[:1],
            "ethnic_group": frame["Race"].fillna("").astype(str).str.upper().str[:1],
            "license": "",
            "county": pd.to_numeric(frame["Co"], errors="coerce"),
            "crime": pd.to_numeric(frame["Cr"], errors="coerce"),
            "accident": frame["Acc"].fillna("").astype(str).str.upper().str[:1],
            "location": frame["Drnk Loc"].fillna("").astype(str),
            "pbt_result": pd.to_numeric(frame["PBT Result"], errors="coerce"),
            "alcohol1char": "",
            "alcohol1": pd.to_numeric(frame["BrAC1 IR"].where(frame["BrAC1 IR"].notna(), frame["BrAC1 EC"]), errors="coerce").mul(1000).round(),
            "alcohol2char": "",
            "alcohol2": pd.to_numeric(frame["BrAC2 IR"].where(frame["BrAC2 IR"].notna(), frame["BrAC2 EC"]), errors="coerce").mul(1000).round(),
        }
    )
    return add_missing_standard_columns(out)


def row_key(frame: pd.DataFrame, cols: list[str]) -> pd.Series:
    pieces = []
    for col in cols:
        if col in {"event_date", "dob"}:
            pieces.append(pd.to_datetime(frame[col], errors="coerce").dt.strftime("%Y-%m-%d").fillna(""))
        elif col in {"alcohol1", "alcohol2", "county", "crime"}:
            pieces.append(pd.to_numeric(frame[col], errors="coerce").round(3).astype("Int64").astype(str).replace("<NA>", ""))
        else:
            pieces.append(frame[col].map(normalize_key_part))
    out = pieces[0]
    for piece in pieces[1:]:
        out = out + "|" + piece
    return out


def dedupe_raw(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = raw.copy()
    frame["subject_norm"] = frame["subject_name"].map(normalize_text)
    frame["citation_norm"] = frame["citation"].map(normalize_text)
    frame["license_norm"] = frame["license"].map(normalize_license)
    frame["low_score_raw"] = frame[["alcohol1", "alcohol2"]].min(axis=1, skipna=True)
    frame["time_sort_seconds"] = frame[["event_time", "test1_blow_time", "test2_blow_time"]].apply(
        lambda col: col.map(time_to_seconds)
    ).max(axis=1, skipna=True)
    frame["source_priority"] = np.where(frame["source_extract"].eq("2026_drop"), 0, 1)

    all_cols = [c for c in STANDARD_RAW_COLUMNS if c not in {"source_extract", "source_record_id"}]
    frame["exact_key"] = row_key(frame, all_cols)
    frame["instrument_event_key"] = row_key(
        frame,
        [
            "source",
            "serial_no",
            "event_date",
            "event_time",
            "citation",
            "subject_name",
            "dob",
            "alcohol1",
            "alcohol2",
        ],
    )
    frame["citation_event_key"] = row_key(
        frame,
        ["source", "event_date", "citation", "subject_name", "dob", "alcohol1", "alcohol2"],
    )
    frame["person_time_event_key"] = row_key(
        frame,
        ["source", "event_date", "event_time", "subject_name", "dob", "alcohol1", "alcohol2"],
    )
    # The 2019 archive keeps a full middle name and a placeholder license value,
    # whereas the 2026 extract often has only a middle initial and no license.
    # For Draeger records, instrument + date + exact time + DOB identifies the
    # same test without relying on those extract-specific fields.
    frame["instrument_person_time_key"] = row_key(
        frame,
        ["source", "serial_no", "event_date", "event_time", "dob"],
    )

    sort_cols = ["source_priority", "source_extract", "source", "event_date", "time_sort_seconds"]
    frame = frame.sort_values(sort_cols, ascending=[True, True, True, True, True]).copy()
    frame["dup_exact"] = frame.duplicated("exact_key", keep="first")
    frame["drop_reason"] = ""
    frame.loc[frame["dup_exact"], "drop_reason"] = "exact_duplicate"

    active = frame["drop_reason"].eq("")
    frame.loc[active, "dup_instrument_event"] = frame.loc[active].duplicated("instrument_event_key", keep="first")
    frame.loc[active & frame["dup_instrument_event"].fillna(False), "drop_reason"] = "instrument_event_duplicate"

    active = frame["drop_reason"].eq("") & frame["citation_norm"].ne("")
    frame.loc[active, "dup_citation_event"] = frame.loc[active].duplicated("citation_event_key", keep="first")
    frame.loc[active & frame["dup_citation_event"].fillna(False), "drop_reason"] = "citation_event_duplicate"

    active = frame["drop_reason"].eq("") & frame["event_time"].fillna("").astype(str).ne("")
    frame.loc[active, "dup_person_time_event"] = frame.loc[active].duplicated("person_time_event_key", keep="first")
    frame.loc[active & frame["dup_person_time_event"].fillna(False), "drop_reason"] = "person_time_event_duplicate"

    active = (
        frame["drop_reason"].eq("")
        & frame["source"].eq("draeger")
        & frame["serial_no"].map(normalize_text).ne("")
        & frame["event_time"].map(normalize_text).ne("")
        & frame["dob"].notna()
    )
    frame.loc[active, "dup_instrument_person_time"] = frame.loc[active].duplicated(
        "instrument_person_time_key", keep="first"
    )
    frame.loc[
        active & frame["dup_instrument_person_time"].fillna(False), "drop_reason"
    ] = "instrument_person_time_duplicate"

    deduped = frame.loc[frame["drop_reason"].eq(""), STANDARD_RAW_COLUMNS].copy()
    audit = pd.DataFrame(
        [
            {"metric": "input_rows", "value": len(raw)},
            {"metric": "dropped_exact_duplicates", "value": int(frame["drop_reason"].eq("exact_duplicate").sum())},
            {
                "metric": "dropped_instrument_event_duplicates",
                "value": int(frame["drop_reason"].eq("instrument_event_duplicate").sum()),
            },
            {"metric": "dropped_citation_event_duplicates", "value": int(frame["drop_reason"].eq("citation_event_duplicate").sum())},
            {
                "metric": "dropped_person_time_event_duplicates",
                "value": int(frame["drop_reason"].eq("person_time_event_duplicate").sum()),
            },
            {
                "metric": "dropped_instrument_person_time_duplicates",
                "value": int(frame["drop_reason"].eq("instrument_person_time_duplicate").sum()),
            },
            {"metric": "deduped_rows", "value": len(deduped)},
        ]
    )
    return deduped.reset_index(drop=True), audit


def prepare_raw_descriptive_observations(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.normalize()
    frame["dob"] = pd.to_datetime(frame["dob"], errors="coerce").dt.normalize()
    frame["low_score"] = frame[["alcohol1", "alcohol2"]].min(axis=1, skipna=True)
    frame = frame[frame["event_date"].notna()].copy()
    frame["year"] = frame["event_date"].dt.year
    frame["dow"] = pd.Categorical(
        frame["event_date"].dt.day_name(),
        categories=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        ordered=True,
    )
    frame["day_of_month"] = frame["event_date"].dt.day
    seconds = frame[["event_time", "test1_blow_time", "test2_blow_time", "observation_start_time"]].apply(
        lambda col: col.map(time_to_seconds)
    ).max(axis=1, skipna=True)
    frame["hour"] = np.floor(seconds / 3600).where(seconds.notna(), np.nan)
    frame["age_at_event"] = (frame["event_date"] - frame["dob"]).dt.days / 365.25
    frame["date_21"] = frame["dob"] + pd.DateOffset(years=21)
    frame["days_to_21"] = (frame["event_date"] - frame["date_21"]).dt.days
    return frame


def audit_washington_person_keys(raw: pd.DataFrame) -> pd.DataFrame:
    """Audit fuzzy candidate pairs without using them to merge people."""
    frame = raw.copy()
    frame["subject_name_clean"] = frame["subject_name"].map(normalize_text)
    frame["operator_clean"] = frame["operator"].map(normalize_text)
    frame["dob"] = pd.to_datetime(frame["dob"], errors="coerce").dt.normalize()
    frame = frame[
        frame["dob"].notna()
        & frame["subject_name_clean"].ne("")
        & ~frame["subject_name_clean"].isin(BAD_SUBJECT_NAMES)
        & ~frame["subject_name_clean"].str.contains("CODE", na=False)
        & frame["subject_name_clean"].ne(frame["operator_clean"])
    ].copy()
    parsed = frame["subject_name"].map(parse_subject_name)
    frame["last_name_norm"] = [p.last for p in parsed]
    frame["first_name_norm"] = [p.first for p in parsed]
    frame["first_initial"] = [p.first_initial for p in parsed]
    frame["middle_initial"] = [p.middle_initial for p in parsed]
    frame = frame[
        frame["last_name_norm"].ne("")
        & frame["first_initial"].ne("")
        & ~frame["last_name_norm"].isin(["TEST", "NEW", "CODE"])
    ].copy()
    dob_str = frame["dob"].dt.strftime("%Y-%m-%d")
    frame["person_key_5l_fmi_dob"] = (
        frame["last_name_norm"].str[:5]
        + "|"
        + frame["first_initial"]
        + "|"
        + frame["middle_initial"].fillna("")
        + "|"
        + dob_str
    )

    people = frame[
        ["person_key_5l_fmi_dob", "last_name_norm", "first_name_norm", "first_initial", "middle_initial", "dob"]
    ].drop_duplicates()
    name_variants = people.groupby("person_key_5l_fmi_dob", sort=False).size()
    candidate_rows: list[dict[str, object]] = []
    for _, group in people.groupby(["dob", "first_initial"], sort=False):
        records = group.to_dict("records")
        for index, left in enumerate(records):
            for right in records[index + 1 :]:
                if left["person_key_5l_fmi_dob"] == right["person_key_5l_fmi_dob"]:
                    continue
                middle_ok = (
                    not left["middle_initial"]
                    or not right["middle_initial"]
                    or left["middle_initial"] == right["middle_initial"]
                )
                last_ratio = SequenceMatcher(None, left["last_name_norm"], right["last_name_norm"]).ratio()
                first_ratio = SequenceMatcher(None, left["first_name_norm"], right["first_name_norm"]).ratio()
                same_prefix = left["last_name_norm"][:5] == right["last_name_norm"][:5]
                fuzzy_candidate = middle_ok and (
                    (last_ratio >= 0.90 and first_ratio >= 0.88) or (same_prefix and first_ratio >= 0.86)
                )
                boundary_case = middle_ok and (
                    (0.85 <= last_ratio < 0.90 and first_ratio >= 0.88)
                    or (last_ratio >= 0.90 and 0.82 <= first_ratio < 0.88)
                    or (same_prefix and 0.82 <= first_ratio < 0.86)
                )
                if not (fuzzy_candidate or boundary_case):
                    continue
                candidate_rows.append(
                    {
                        "review_status": "fuzzy_candidate" if fuzzy_candidate else "boundary_not_merged",
                        "match_basis": "same_last5_prefix" if same_prefix else "high_name_similarity",
                        "last_name_similarity": last_ratio,
                        "first_name_similarity": first_ratio,
                        "middle_initial_compatible": middle_ok,
                        "person_key_left": left["person_key_5l_fmi_dob"],
                        "last_name_left": left["last_name_norm"],
                        "first_name_left": left["first_name_norm"],
                        "middle_initial_left": left["middle_initial"],
                        "person_key_right": right["person_key_5l_fmi_dob"],
                        "last_name_right": right["last_name_norm"],
                        "first_name_right": right["first_name_norm"],
                        "middle_initial_right": right["middle_initial"],
                        "dob": left["dob"],
                    }
                )

    private_matches = pd.DataFrame(candidate_rows)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    private_matches.to_csv(PRIVATE_DIR / "washington_key_borderline_matches.csv", index=False)
    summary = pd.DataFrame(
        [
            {"metric": "eligible_test_rows", "value": len(frame)},
            {"metric": "washington_person_keys", "value": frame["person_key_5l_fmi_dob"].nunique()},
            {"metric": "distinct_name_variants", "value": len(people)},
            {"metric": "washington_keys_with_multiple_name_variants", "value": int(name_variants.gt(1).sum())},
            {
                "metric": "fuzzy_candidate_pairs_audit_only",
                "value": int(private_matches["review_status"].eq("fuzzy_candidate").sum()) if not private_matches.empty else 0,
            },
            {
                "metric": "boundary_pairs_not_merged",
                "value": int(private_matches["review_status"].eq("boundary_not_merged").sum()) if not private_matches.empty else 0,
            },
        ]
    )
    summary.to_csv(TABLE_DIR / "person_linkage_audit.csv", index=False)
    return summary


def build_washington_person_day_panel(raw: pd.DataFrame) -> pd.DataFrame:
    """Create one selected breath-test record per Washington person-day."""
    frame = raw.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.normalize()
    frame["dob"] = pd.to_datetime(frame["dob"], errors="coerce").dt.normalize()
    frame["subject_name_clean"] = frame["subject_name"].map(normalize_text)
    frame["operator_clean"] = frame["operator"].map(normalize_text)
    frame = frame[
        frame["event_date"].notna()
        & frame["dob"].notna()
        & frame["crime"].notna()
        & frame["subject_name_clean"].ne("")
        & ~frame["subject_name_clean"].isin(BAD_SUBJECT_NAMES)
        & ~frame["subject_name_clean"].str.contains("CODE", na=False)
        & frame["subject_name_clean"].ne(frame["operator_clean"])
    ].copy()
    parsed = frame["subject_name"].map(parse_subject_name)
    frame["last_name_norm"] = [p.last for p in parsed]
    frame["first_name_norm"] = [p.first for p in parsed]
    frame["first_initial"] = [p.first_initial for p in parsed]
    frame["middle_initial"] = [p.middle_initial for p in parsed]
    frame = frame[
        frame["last_name_norm"].ne("")
        & frame["first_initial"].ne("")
        & ~frame["last_name_norm"].isin(["TEST", "NEW", "CODE"])
    ].copy()
    dob_str = frame["dob"].dt.strftime("%Y-%m-%d")
    frame["person_key_5l_fmi_dob"] = (
        frame["last_name_norm"].str[:5]
        + "|"
        + frame["first_initial"]
        + "|"
        + frame["middle_initial"].fillna("")
        + "|"
        + dob_str
    )
    frame["person_key_5l_fi_dob"] = frame["last_name_norm"].str[:5] + "|" + frame["first_initial"] + "|" + dob_str
    frame["person_id_wa"] = pd.factorize(frame["person_key_5l_fmi_dob"], sort=True)[0] + 1

    frame["alcohol1"] = pd.to_numeric(frame["alcohol1"], errors="coerce")
    frame["alcohol2"] = pd.to_numeric(frame["alcohol2"], errors="coerce")
    frame.loc[(frame["alcohol1"] > 0) & frame["alcohol2"].fillna(0).eq(0), "alcohol2"] = np.nan
    frame.loc[frame["alcohol1"].fillna(0).eq(0) & (frame["alcohol2"] > 0), "alcohol2"] = np.nan
    frame["pair_diff_abs"] = (frame["alcohol1"] - frame["alcohol2"]).abs()
    frame["has_two_numeric_tests"] = frame["alcohol1"].notna() & frame["alcohol2"].notna()
    frame["pair_gap_gt_20"] = (frame["has_two_numeric_tests"] & frame["pair_diff_abs"].gt(20)).astype(int)
    frame["pair_gap_le_20"] = (frame["has_two_numeric_tests"] & frame["pair_diff_abs"].le(20)).astype(int)
    frame["row_low_score"] = frame[["alcohol1", "alcohol2"]].min(axis=1, skipna=True)
    time_columns = ["event_time", "test1_blow_time", "test2_blow_time", "observation_start_time"]
    frame["row_sort_seconds"] = frame[time_columns].apply(lambda column: column.map(time_to_seconds)).max(axis=1, skipna=True).fillna(-1)

    person_day = ["person_id_wa", "event_date"]
    grouped = frame.groupby(person_day, sort=False)
    frame["same_day_row_count"] = grouped["person_id_wa"].transform("size")
    frame["has_same_day_retest_line"] = frame["same_day_row_count"].gt(1).astype(int)
    frame["any_same_day_pair_gap_gt_20"] = grouped["pair_gap_gt_20"].transform("max")
    frame["any_same_day_admissible_pair"] = grouped["pair_gap_le_20"].transform("max")
    frame["same_day_legacy_low_score"] = grouped["row_low_score"].transform("min")

    selected = (
        frame.sort_values(
            person_day + ["any_same_day_admissible_pair", "pair_gap_le_20", "row_sort_seconds", "source", "serial_no", "citation"],
            ascending=[True, True, False, False, False, True, True, True],
        )
        .drop_duplicates(person_day, keep="first")
        .copy()
    )
    selected["low_score"] = np.where(
        selected["any_same_day_admissible_pair"].eq(1),
        selected["row_low_score"],
        selected["same_day_legacy_low_score"],
    )
    selected["low_score_mod"] = np.where(
        selected["low_score"].notna(), selected["low_score"] - np.mod(selected["low_score"], 2), np.nan
    )
    selected["selected_row_pair_gap_gt_20"] = selected["pair_gap_gt_20"]
    selected["selected_row_pair_gap_le_20"] = selected["pair_gap_le_20"]
    selected["selected_row_has_two_numeric_tests"] = selected["has_two_numeric_tests"].astype(int)
    selected["selected_row_is_latest_same_day"] = 1
    selected["selected_row_low_score"] = selected["row_low_score"]
    selected["year"] = selected["event_date"].dt.year
    selected["male"] = selected["sex"].astype(str).str.upper().eq("M").astype(int)
    selected["white"] = selected["ethnic_group"].astype(str).str.upper().eq("W").astype(int)
    selected = selected.rename(
        columns={
            "event_date": "Date",
            "serial_no": "SerialNo",
            "citation": "Citation",
            "subject_name": "SubjectName",
            "license": "License",
        }
    )
    return selected


def recompute_repeat_outcomes(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["low_score"] = pd.to_numeric(frame["low_score"], errors="coerce")
    # The legacy panel is one row per legacy name/day. Re-collapse by the
    # Washington person key so a same-day name variant cannot interrupt the
    # next-offense sequence.
    frame = (
        frame.sort_values(
            [
                "person_id_wa",
                "Date",
                "any_same_day_admissible_pair",
                "selected_row_pair_gap_le_20",
                "SerialNo",
                "Citation",
            ],
            ascending=[True, True, False, False, True, True],
        )
        .drop_duplicates(["person_id_wa", "Date"], keep="first")
        .copy()
    )
    frame["offense_wa"] = frame.groupby("person_id_wa").cumcount() + 1
    frame["total_dui_wa"] = frame.groupby("person_id_wa")["offense_wa"].transform("max") - 1
    frame["next_breath_date_wa"] = frame.groupby("person_id_wa")["Date"].shift(-1)
    frame["next_breath_bac_wa"] = frame.groupby("person_id_wa")["low_score"].shift(-1)
    days_next = (frame["next_breath_date_wa"] - frame["Date"]).dt.days
    frame["days_to_next_breath_wa"] = days_next
    frame["recidivism_4y_wa"] = ((days_next > 0) & (days_next <= FOLLOWUP_DAYS)).astype(int)
    frame["low_bac"] = frame["low_score"] / 1000
    frame["low_bac_bin"] = pd.to_numeric(frame["low_score_mod"], errors="coerce") / 1000
    frame["age_at_event"] = (frame["Date"] - pd.to_datetime(frame["dob"], errors="coerce")).dt.days / 365.25
    return frame


def export_stata_rd_input(panel: pd.DataFrame) -> None:
    STATA_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    stata = panel[["Date", "low_score", "age_at_event", "crime", "recidivism_4y_wa"]].copy()
    stata = stata.rename(columns={"Date": "event_date"})
    stata["event_date"] = (pd.to_datetime(stata["event_date"]) - pd.Timestamp("1960-01-01")).dt.days.astype("Int32")
    stata["recidivism_4y_wa"] = stata["recidivism_4y_wa"].astype("int8")
    stata.to_stata(STATA_RD_INPUT, write_index=False, version=118)


def make_analysis_samples(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    max_date = panel["Date"].max()
    full_followup_cutoff = max_date - pd.Timedelta(days=FOLLOWUP_DAYS)
    base = panel[
        panel["Date"].notna()
        & panel["dob"].notna()
        & panel["low_bac"].notna()
        & panel["crime"].isin([1, 3])
        & panel["Date"].le(full_followup_cutoff)
    ].copy()

    samples: dict[str, pd.DataFrame] = {}
    for label, start, end in [
        ("1999_2008", pd.Timestamp("1999-01-01"), pd.Timestamp("2008-12-31")),
        ("1999_2022_full4y", pd.Timestamp("1999-01-01"), min(pd.Timestamp("2022-12-31"), full_followup_cutoff)),
        ("2009_2022_full4y", pd.Timestamp("2009-01-01"), min(pd.Timestamp("2022-12-31"), full_followup_cutoff)),
    ]:
        cohort = base[base["Date"].between(start, end, inclusive="both")].copy()
        adult = cohort[
            cohort["age_at_event"].ge(21)
            & cohort["crime"].eq(1)
            & cohort["low_bac"].between(ADULT_MIN_BAC, MAX_BAC, inclusive="both")
        ].copy()
        youth = cohort[
            cohort["age_at_event"].ge(18)
            & cohort["age_at_event"].lt(21)
            & cohort["crime"].isin([1, 3])
            & cohort["low_bac"].between(YOUTH_MIN_BAC, MAX_BAC, inclusive="both")
        ].copy()
        samples[f"adult_{label}"] = adult
        samples[f"youth_{label}"] = youth
    return samples


def build_threshold_binned(panel: pd.DataFrame) -> pd.DataFrame:
    samples = make_analysis_samples(panel)
    bin_rows = []
    cohorts = ["1999_2008", "1999_2022_full4y", "2009_2022_full4y"]
    for population in ["adult", "youth"]:
        for cohort in cohorts:
            sample = samples[f"{population}_{cohort}"]
            binned = (
                sample.groupby("low_bac_bin", as_index=False)
                .agg(n=("Date", "size"), recid_rate=("recidivism_4y_wa", "mean"))
                .rename(columns={"low_bac_bin": "bac_bin"})
            )
            binned["population"] = population
            binned["cohort"] = cohort
            bin_rows.append(binned)
    return pd.concat(bin_rows, ignore_index=True)


def build_age21_binned_tables(
    desc: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    around21 = desc[desc["days_to_21"].between(-730, 730, inclusive="both")].copy()
    if start_date is not None:
        around21 = around21[around21["event_date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        around21 = around21[around21["event_date"] <= pd.Timestamp(end_date)]

    age21_daily = around21.groupby("days_to_21", as_index=False).size().rename(columns={"size": "tests"})
    around21["days_to_21_week_bin"] = np.floor(around21["days_to_21"] / 7).astype(int) * 7
    age21_weekly = around21.groupby("days_to_21_week_bin", as_index=False).size().rename(columns={"size": "tests"})
    age21_weekly = age21_weekly[age21_weekly["days_to_21_week_bin"].between(-728, 721, inclusive="both")].copy()
    age21_weekly["days_to_21"] = age21_weekly["days_to_21_week_bin"] + 3.5
    around21["days_to_21_28day_bin"] = np.floor(around21["days_to_21"] / 28).astype(int) * 28
    age21_28day = around21.groupby("days_to_21_28day_bin", as_index=False).size().rename(columns={"size": "tests"})
    age21_28day = age21_28day[age21_28day["days_to_21_28day_bin"].between(-728, 700, inclusive="both")].copy()
    age21_28day["days_to_21"] = age21_28day["days_to_21_28day_bin"] + 14
    return {"daily": age21_daily, "weekly": age21_weekly, "28day": age21_28day}


def save_descriptive_tables(raw: pd.DataFrame, panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    desc = prepare_raw_descriptive_observations(raw)
    daily = desc.groupby("event_date", as_index=False).size().rename(columns={"size": "tests"})
    daily["tests_28d_ma"] = daily["tests"].rolling(28, min_periods=1, center=True).mean()
    dow = desc.groupby("dow", observed=False, as_index=False).size().rename(columns={"size": "tests"})
    dom = desc.groupby("day_of_month", as_index=False).size().rename(columns={"size": "tests"})
    hour = desc.dropna(subset=["hour"]).groupby("hour", as_index=False).size().rename(columns={"size": "tests"})
    age21 = build_age21_binned_tables(desc)

    person_summary = pd.DataFrame(
        [
            {"metric": "person_day_events", "value": len(panel)},
            {"metric": "washington_5l_fmi_dob_ids", "value": panel["person_key_5l_fmi_dob"].nunique()},
            {"metric": "washington_person_ids", "value": panel["person_id_wa"].nunique()},
            {"metric": "max_event_date", "value": panel["Date"].max().date().isoformat()},
            {"metric": "full_4y_index_cutoff", "value": (panel["Date"].max() - pd.Timedelta(days=FOLLOWUP_DAYS)).date().isoformat()},
        ]
    )

    outputs = {
        "daily_tests": daily,
        "tests_by_day_of_week": dow,
        "tests_by_day_of_month": dom,
        "tests_by_hour": hour,
        "tests_relative_to_21_daily": age21["daily"],
        "tests_relative_to_21_weekly": age21["weekly"],
        "tests_relative_to_21_28day": age21["28day"],
        "person_identifier_summary": person_summary,
    }
    for sample, sample_desc in [
        ("bac_positive", desc[desc["low_score"].gt(0)]),
        ("accident", desc[desc["accident"].eq("Y")]),
    ]:
        for bin_width, frame in build_age21_binned_tables(sample_desc).items():
            outputs[f"tests_relative_to_21_{sample}_{bin_width}"] = frame
    for period, start_date, end_date in [
        ("1999_to_june_2014", "1999-01-01", "2014-06-30"),
        ("july_2014_to_present", "2014-07-01", None),
    ]:
        for bin_width, frame in build_age21_binned_tables(desc, start_date, end_date).items():
            outputs[f"tests_relative_to_21_{period}_{bin_width}"] = frame
    for name, frame in outputs.items():
        frame.to_csv(TABLE_DIR / f"{name}.csv", index=False)
    return outputs


def clean_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=PLOT_TEXT)
    ax.title.set_color(PLOT_TEXT)


def plot_descriptives(tables: dict[str, pd.DataFrame]) -> None:
    daily = tables["daily_tests"]
    fig, ax = plt.subplots(figsize=(13, 4.8))
    ax.plot(daily["event_date"], daily["tests"], color="#b8c7d9", linewidth=0.5, label="Daily")
    ax.plot(daily["event_date"], daily["tests_28d_ma"], color=PLOT_BLUE, linewidth=1.7, label="28-day moving average")
    ax.set_title("Breath Tests by Date")
    ax.set_ylabel("Tests")
    ax.legend(frameon=False, loc="upper left")
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "daily_tests_1995_2026.svg", bbox_inches="tight")
    plt.close(fig)

    dow = tables["tests_by_day_of_week"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(dow["dow"].astype(str), dow["tests"], color=PLOT_BLUE)
    ax.set_title("Breath Tests by Day of Week")
    ax.set_ylabel("Tests")
    ax.tick_params(axis="x", rotation=35)
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "tests_by_day_of_week.svg", bbox_inches="tight")
    plt.close(fig)

    dom = tables["tests_by_day_of_month"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(dom["day_of_month"], dom["tests"], color=PLOT_BLUE)
    ax.set_title("Breath Tests by Day of Month")
    ax.set_xlabel("Day of month")
    ax.set_ylabel("Tests")
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "tests_by_day_of_month.svg", bbox_inches="tight")
    plt.close(fig)

    hour = tables["tests_by_hour"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(hour["hour"], hour["tests"], color=PLOT_BLUE)
    ax.set_title("Breath Tests by Hour of Day")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Tests")
    ax.set_xticks(range(0, 24, 2))
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "tests_by_hour.svg", bbox_inches="tight")
    plt.close(fig)

    for table_name, label, filename, x_limits in [
        ("tests_relative_to_21_daily", "Daily observations", "tests_relative_to_turning_21_daily.svg", (-730, 730)),
        ("tests_relative_to_21_weekly", "7-day bins", "tests_relative_to_turning_21_weekly.svg", (-728, 728)),
        ("tests_relative_to_21_28day", "28-day bins", "tests_relative_to_turning_21_28day.svg", (-728, 728)),
    ]:
        age21 = tables[table_name]
        fig, ax = plt.subplots(figsize=(9.6, 4.6))
        ax.scatter(age21["days_to_21"], age21["tests"], s=12, color=PLOT_BLUE)
        ax.axvline(0, color=PLOT_TEXT, linestyle="--", linewidth=1.0)
        ax.set_xlim(*x_limits)
        ax.set_title(f"Breath-Test Observations Relative to Turning 21 ({label})")
        ax.set_xlabel("Days from 21st birthday")
        ax.set_ylabel("Observations")
        clean_axes(ax)
        fig.tight_layout()
        fig.savefig(FIG_DIR / filename, bbox_inches="tight")
        plt.close(fig)

    for sample, sample_label in [
        ("bac_positive", "Breath-Test Observations with BAC > 0"),
        ("accident", "Breath-Test Observations with a Recorded Collision"),
    ]:
        for bin_width, label, x_limits in [
            ("daily", "Daily observations", (-730, 730)),
            ("weekly", "7-day bins", (-728, 728)),
            ("28day", "28-day bins", (-728, 728)),
        ]:
            age21 = tables[f"tests_relative_to_21_{sample}_{bin_width}"]
            fig, ax = plt.subplots(figsize=(9.6, 4.6))
            ax.scatter(age21["days_to_21"], age21["tests"], s=12, color=PLOT_BLUE)
            ax.axvline(0, color=PLOT_TEXT, linestyle="--", linewidth=1.0)
            ax.set_xlim(*x_limits)
            ax.set_title(f"{sample_label} Relative to Turning 21 ({label})")
            ax.set_xlabel("Days from 21st birthday")
            ax.set_ylabel("Observations")
            clean_axes(ax)
            fig.tight_layout()
            fig.savefig(FIG_DIR / f"tests_relative_to_turning_21_{sample}_{bin_width}.svg", bbox_inches="tight")
            plt.close(fig)

    period_specs = [
        ("1999_to_june_2014", "1999-June 2014"),
        ("july_2014_to_present", "July 2014-present"),
    ]
    bin_specs = [
        ("daily", "Daily observations", (-730, 730)),
        ("weekly", "7-day bins", (-728, 728)),
        ("28day", "28-day bins", (-728, 728)),
    ]
    for bin_width, label, x_limits in bin_specs:
        period_tables = [tables[f"tests_relative_to_21_{period}_{bin_width}"] for period, _ in period_specs]
        y_max = np.ceil(max(frame["tests"].max() for frame in period_tables) * 1.05)
        for period, period_label in period_specs:
            age21 = tables[f"tests_relative_to_21_{period}_{bin_width}"]
            fig, ax = plt.subplots(figsize=(9.6, 4.6))
            ax.scatter(age21["days_to_21"], age21["tests"], s=12, color=PLOT_BLUE)
            ax.axvline(0, color=PLOT_TEXT, linestyle="--", linewidth=1.0)
            ax.set_xlim(*x_limits)
            ax.set_ylim(0, y_max)
            ax.set_title(f"Breath-Test Observations Relative to Turning 21 ({period_label}; {label})")
            ax.set_xlabel("Days from 21st birthday")
            ax.set_ylabel("Observations")
            clean_axes(ax)
            fig.tight_layout()
            fig.savefig(FIG_DIR / f"tests_relative_to_turning_21_{period}_{bin_width}.svg", bbox_inches="tight")
            plt.close(fig)


def plot_threshold_figures(binned: pd.DataFrame) -> None:
    for population, threshold in [("adult", 0.08), ("youth", 0.02)]:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
        for ax, cohort in zip(axes, ["1999_2008", "1999_2022_full4y"]):
            sub = binned[(binned["population"].eq(population)) & (binned["cohort"].eq(cohort))].copy()
            if population == "adult":
                sub = sub[sub["bac_bin"].between(0.03, 0.20, inclusive="both")]
                ax.set_xlim(0.03, 0.20)
            else:
                sub = sub[sub["bac_bin"].between(0.0, 0.20, inclusive="both")]
                ax.set_xlim(0.0, 0.20)
            ax.scatter(sub["bac_bin"], sub["recid_rate"] * 100, s=np.clip(sub["n"], 15, 150), facecolors="none", edgecolors=PLOT_BLUE)
            ax.axvline(threshold, color=PLOT_TEXT, linestyle="--", linewidth=1.0, label=".08 DUI per se" if population == "adult" else ".02 zero tolerance")
            if population == "adult":
                ax.axvline(0.15, color=PLOT_GOLD, linestyle=":", linewidth=1.3, label=".15 aggravated DUI")
            else:
                ax.axvline(0.08, color=PLOT_GOLD, linestyle=":", linewidth=1.3, label=".08 criminal threshold")
                ax.axvline(0.15, color="#6b8e23", linestyle="-.", linewidth=1.2, label=".15 aggravated DUI")
            ax.set_title(cohort.replace("_full4y", " full 4y").replace("_", "-"))
            ax.set_xlabel("BAC")
            clean_axes(ax)
        axes[0].set_ylabel("Repeat breath test within 4 years (%)")
        axes[0].legend(frameon=False, loc="upper right")
        fig.suptitle(f"{population.title()} BAC Threshold and Repeat Testing", y=1.02)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"{population}_threshold_recidivism.svg", bbox_inches="tight")
        plt.close(fig)

    sub = binned[
        binned["population"].eq("adult")
        & binned["cohort"].eq("2009_2022_full4y")
        & binned["bac_bin"].between(0.03, 0.20, inclusive="both")
    ].copy()
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    ax.scatter(sub["bac_bin"], sub["recid_rate"] * 100, s=np.clip(sub["n"], 15, 150), facecolors="none", edgecolors=PLOT_BLUE)
    ax.axvline(0.08, color=PLOT_TEXT, linestyle="--", linewidth=1.0, label=".08 DUI per se")
    ax.axvline(0.15, color=PLOT_GOLD, linestyle=":", linewidth=1.3, label=".15 aggravated DUI")
    ax.set_xlim(0.03, 0.20)
    ax.set_title("Adult BAC and Repeat Testing, 2009-2022")
    ax.set_xlabel("BAC")
    ax.set_ylabel("Repeat breath test within 4 years (%)")
    ax.legend(frameon=False, loc="upper right")
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "adult_threshold_recidivism_2009_2022.svg", bbox_inches="tight")
    plt.close(fig)


def plot_rd_estimates(rd: pd.DataFrame) -> None:
    cohort_labels = {
        "1999_2008": "1999-2008",
        "1999_2022_full4y": "1999-2022",
        "2009_2022_full4y": "2009-2022",
    }
    for population, thresholds in [("adult", [0.08, 0.15]), ("youth", [0.02, 0.08, 0.15])]:
        sub = rd[rd["population"].eq(population)].copy()
        sub["threshold_order"] = pd.Categorical(sub["threshold_bac"], thresholds, ordered=True)
        sub["cohort_order"] = pd.Categorical(
            sub["cohort"], ["1999_2008", "1999_2022_full4y", "2009_2022_full4y"], ordered=True
        )
        sub = sub.sort_values(["threshold_order", "cohort_order"], ascending=[False, True]).reset_index(drop=True)
        y = np.arange(len(sub))
        fig, ax = plt.subplots(figsize=(8.8, 4.0 if population == "adult" else 5.2))
        ax.errorbar(
            sub["coef"] * 100,
            y,
            xerr=1.96 * sub["se"] * 100,
            fmt="o",
            markersize=5.5,
            capsize=3,
            color=PLOT_BLUE,
            ecolor=PLOT_BLUE,
            linewidth=1.2,
        )
        ax.axvline(0, color=PLOT_TEXT, linestyle="--", linewidth=1.0)
        ax.set_yticks(y, [f"BAC {threshold:.2f} | {cohort_labels[cohort]}" for threshold, cohort in zip(sub["threshold_bac"], sub["cohort"])])
        ax.set_xlabel("Estimated discontinuity in 4-year repeat breath test (percentage points)")
        ax.set_title(f"{population.title()} BAC Threshold RD Estimates")
        ax.text(
            0,
            -0.18,
            "Local-linear RD, inclusive +/-0.05 BAC bandwidth; 95% confidence intervals use cluster-robust SEs.",
            transform=ax.transAxes,
            color=PLOT_TEXT,
            fontsize=8.5,
            ha="left",
        )
        clean_axes(ax)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"{population}_threshold_rd_estimates_h0p05.svg", bbox_inches="tight")
        plt.close(fig)


def write_markdown(raw_audit: pd.DataFrame, panel: pd.DataFrame, rd: pd.DataFrame) -> None:
    audit = raw_audit.set_index("metric")["value"].to_dict()
    max_date = pd.to_datetime(panel["Date"], errors="coerce").max()
    cutoff = max_date - pd.Timedelta(days=FOLLOWUP_DAYS)
    rd_display = rd.copy()
    for col in ["coef", "se", "p_value", "mean_below", "mean_above"]:
        rd_display[col] = pd.to_numeric(rd_display[col], errors="coerce").map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
    rd_display["n"] = pd.to_numeric(rd_display["n"], errors="coerce").astype("Int64").astype(str)

    md = [
        "# Breath panel update through 2026",
        "",
        "This package imports the new `R006001-040926_DB_REDACTED.xlsx` breath-test workbook, combines it with the previously standardized 1995-2019 extract, removes duplicate raw observations, rebuilds the person-day breath panel, and creates first-pass descriptives and repeat-offending threshold checks.",
        "",
        "## Duplicate audit",
        "",
        f"- Raw rows before de-duplication: `{int(audit['input_rows']):,}`.",
        f"- Exact duplicates dropped: `{int(audit['dropped_exact_duplicates']):,}`.",
        f"- Instrument/date/time/citation/name duplicates dropped: `{int(audit['dropped_instrument_event_duplicates']):,}`.",
        f"- Citation-event duplicates dropped: `{int(audit['dropped_citation_event_duplicates']):,}`.",
        f"- Person-time-event duplicates dropped: `{int(audit['dropped_person_time_event_duplicates']):,}`.",
        f"- Raw rows retained for descriptives/panel building: `{int(audit['deduped_rows']):,}`.",
        "",
        "## Person panel",
        "",
        f"- Person-day events in rebuilt panel: `{len(panel):,}`.",
        f"- Event dates run through `{max_date.date().isoformat()}`; full 4-year follow-up index events run through `{cutoff.date().isoformat()}`.",
        "- Recidivism uses `person_id_wa`, a factorized version of `person_key_5l_fmi_dob`: first five letters of last name, first initial, middle initial, and DOB.",
        "- Fuzzy comparisons are audit-only and are never used to merge people in the recidivism outcome.",
        "",
        "## Threshold checks",
        "",
        "```csv",
        rd_display.to_csv(index=False).strip(),
        "```",
        "",
        "## Files",
        "",
        f"- `standardized_breath_raw_1995_2026_dedup.parquet`",
        f"- `breath_panel_1995_2026.parquet`",
        f"- `breath_panel_1995_2026.csv.gz`",
        f"- `tables/raw_duplicate_audit.csv`",
        f"- `tables/person_linkage_audit.csv`",
        f"- `tables/threshold_recidivism_rd.csv`",
        f"- `figures/daily_tests_1995_2026.svg`",
        f"- `figures/tests_by_day_of_week.svg`",
        f"- `figures/tests_by_day_of_month.svg`",
        f"- `figures/tests_by_hour.svg`",
        f"- `figures/tests_relative_to_turning_21_daily.svg`",
        f"- `figures/tests_relative_to_turning_21_weekly.svg`",
        f"- `figures/tests_relative_to_turning_21_28day.svg`",
        f"- `figures/tests_relative_to_turning_21_1999_to_june_2014_daily.svg`",
        f"- `figures/tests_relative_to_turning_21_1999_to_june_2014_weekly.svg`",
        f"- `figures/tests_relative_to_turning_21_1999_to_june_2014_28day.svg`",
        f"- `figures/tests_relative_to_turning_21_july_2014_to_present_daily.svg`",
        f"- `figures/tests_relative_to_turning_21_july_2014_to_present_weekly.svg`",
        f"- `figures/tests_relative_to_turning_21_july_2014_to_present_28day.svg`",
        f"- `figures/adult_threshold_recidivism.svg`",
        f"- `figures/youth_threshold_recidivism.svg`",
        f"- `figures/adult_threshold_rd_estimates_h0p05.svg`",
        f"- `figures/youth_threshold_rd_estimates_h0p05.svg`",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main(raw_only: bool = False, linkage_audit_only: bool = False, use_cached_raw: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    if use_cached_raw:
        if not OUT_RAW.exists():
            raise FileNotFoundError(f"Cached raw panel not found: {OUT_RAW}")
        raw_dedup = pd.read_parquet(OUT_RAW)
        audit = pd.read_csv(TABLE_DIR / "raw_duplicate_audit.csv")
    else:
        old_raw = read_old_standardized_raw()
        new_raw = pd.concat([read_new_datamaster(), read_new_draeger()], ignore_index=True)
        raw = pd.concat([old_raw, new_raw], ignore_index=True)
        raw_dedup, audit = dedupe_raw(raw)
        audit.to_csv(TABLE_DIR / "raw_duplicate_audit.csv", index=False)
        raw_dedup.to_parquet(OUT_RAW, index=False)

    if linkage_audit_only:
        audit_washington_person_keys(raw_dedup)
        print(f"Wrote Washington-key linkage audit to {TABLE_DIR} and {PRIVATE_DIR}")
        return

    if raw_only:
        print(f"Wrote de-duplicated raw breath records to {OUT_RAW}")
        return

    panel = build_washington_person_day_panel(raw_dedup)
    panel = recompute_repeat_outcomes(panel)
    panel.to_parquet(OUT_PANEL_PARQUET, index=False)
    panel.to_csv(OUT_PANEL_CSV, index=False, compression="gzip")
    export_stata_rd_input(panel)

    raw_source_years = (
        raw_dedup.groupby(["source_extract", "source", raw_dedup["event_date"].dt.year], as_index=False)
        .size()
        .rename(columns={"event_date": "year", "size": "rows"})
    )
    raw_source_years.to_csv(TABLE_DIR / "source_years_after_dedup.csv", index=False)

    tables = save_descriptive_tables(raw_dedup, panel)
    plot_descriptives(tables)

    binned = build_threshold_binned(panel)
    binned.to_csv(TABLE_DIR / "threshold_recidivism_binned.csv", index=False)
    plot_threshold_figures(binned)

    print(f"Wrote 2026 breath update package to {OUT_DIR}")
    print(f"Run Stata estimation with {ROOT / '2026' / 'code' / 'analysis' / 'estimate_breath_threshold_rd_stata19.do'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Rebuild only the de-duplicated raw extract and duplicate audit.",
    )
    parser.add_argument(
        "--linkage-audit-only",
        action="store_true",
        help="Audit Washington person-key borderline matches without rebuilding the person-day panel.",
    )
    parser.add_argument(
        "--use-cached-raw",
        action="store_true",
        help="Build panel outputs from the cached de-duplicated raw parquet instead of re-importing source files.",
    )
    args = parser.parse_args()
    main(raw_only=args.raw_only, linkage_audit_only=args.linkage_audit_only, use_cached_raw=args.use_cached_raw)
