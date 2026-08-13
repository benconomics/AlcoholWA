from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BREATH_PATH = ROOT / "Older" / "dui_analysis.dta"
COURT_PATH = ROOT / "Older" / "punishments_offenders.dta"
OUT_DIR = ROOT / "breath_bac_recidivism_linkage"
OUT_FIG = OUT_DIR / "bac_recidivism_three_panel.svg"
OUT_BINNED = OUT_DIR / "bac_recidivism_binned.csv"
OUT_LINKED = OUT_DIR / "breath_to_court_linked_events.csv"
OUT_MATCH_SUMMARY = OUT_DIR / "breath_to_court_match_summary.csv"
OUT_MD = OUT_DIR / "breath_bac_recidivism_linkage.md"

BAC_MIN = 0.03
BAC_MAX = 0.20
FOLLOWUP_COHORT_END_YEAR = 2007
LEGAL_AGE = 21
DATE_WINDOW_DAYS = 2
DOB_SHIFT_DAYS = (365, 366)

PLOT_GROUPS = [
    ("overall", "All offenders"),
    ("first_time", "First-time offenders"),
    ("repeat", "Repeat offenders"),
]

SCATTER_COLOR = "#1f4e79"
LINE_COLOR = "#111111"
THRESHOLD_LINES = (0.08, 0.15)


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


def to_datetime_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series).dt.normalize()
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.to_datetime(numeric, unit="D", origin="1960-01-01", errors="coerce").dt.normalize()


def safe_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


@dataclass
class ParsedName:
    full_name_norm: str
    last_name_norm: str
    first_name_norm: str
    first_initial: str
    middle_initial: str


def parse_breath_name(value: object) -> ParsedName:
    raw = "" if pd.isna(value) else str(value).strip()
    raw = raw.replace(",", "/")
    parts = [normalize_name_token(part) for part in raw.split("/") if normalize_name_token(part)]
    last = parts[0] if parts else ""
    first = parts[1] if len(parts) > 1 else ""
    middle = parts[2][0] if len(parts) > 2 and parts[2] else ""
    full_name = " ".join(part for part in [last, first, middle] if part)
    return ParsedName(
        full_name_norm=full_name,
        last_name_norm=last,
        first_name_norm=first,
        first_initial=first[:1],
        middle_initial=middle,
    )


def parse_court_name(value: object) -> ParsedName:
    raw_value = "" if pd.isna(value) else str(value).strip()
    if "," in raw_value:
        last_part, rest = raw_value.split(",", 1)
        last = normalize_name_token(last_part)
        rest_tokens = [normalize_name_token(token) for token in normalize_text(rest).split(" ") if normalize_name_token(token)]
    else:
        tokens = [normalize_name_token(token) for token in normalize_text(raw_value).split(" ") if normalize_name_token(token)]
        last = tokens[0] if tokens else ""
        rest_tokens = tokens[1:]
    first = rest_tokens[0] if rest_tokens else ""
    middle = rest_tokens[1][:1] if len(rest_tokens) > 1 and rest_tokens[1] else ""
    full_name = " ".join(part for part in [last, first, middle] if part)
    return ParsedName(
        full_name_norm=full_name,
        last_name_norm=last,
        first_name_norm=first,
        first_initial=first[:1],
        middle_initial=middle,
    )


def prepare_breath_panel() -> pd.DataFrame:
    cols = [
        "Date",
        "dob",
        "SubjectName",
        "License",
        "low_score",
        "low_score_mod",
        "recidivism",
        "recid_bac",
        "recid_date",
        "crime",
        "offense",
        "year",
    ]
    frame = pd.read_stata(BREATH_PATH, convert_categoricals=False, columns=cols)
    frame["event_date"] = to_datetime_series(frame["Date"])
    frame["dob_date"] = to_datetime_series(frame["dob"])
    frame["recid_date"] = to_datetime_series(frame["recid_date"])
    frame["low_bac"] = pd.to_numeric(frame["low_score"], errors="coerce") / 1000
    frame["low_bac_bin"] = pd.to_numeric(frame["low_score_mod"], errors="coerce") / 1000
    frame["future_bac"] = pd.to_numeric(frame["recid_bac"], errors="coerce") / 1000
    frame["recidivism"] = pd.to_numeric(frame["recidivism"], errors="coerce").fillna(0).astype(int)
    frame["crime"] = pd.to_numeric(frame["crime"], errors="coerce")
    frame["offense"] = pd.to_numeric(frame["offense"], errors="coerce")
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["license_norm"] = frame["License"].map(normalize_license)

    parsed = frame["SubjectName"].map(parse_breath_name)
    frame["subject_name_norm"] = [item.full_name_norm for item in parsed]
    frame["last_name_norm"] = [item.last_name_norm for item in parsed]
    frame["first_name_norm"] = [item.first_name_norm for item in parsed]
    frame["first_initial"] = [item.first_initial for item in parsed]
    frame["middle_initial"] = [item.middle_initial for item in parsed]

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


def prepare_scatter_sample(frame: pd.DataFrame) -> pd.DataFrame:
    sample = frame[frame["year"].le(FOLLOWUP_COHORT_END_YEAR)].copy()
    sample["group"] = "overall"
    return sample


def build_binned_summary(sample: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    group_frames = {
        "overall": sample.copy(),
        "first_time": sample[sample["offense"].eq(1)].copy(),
        "repeat": sample[sample["offense"].ge(2)].copy(),
    }
    for group_key, group_label in PLOT_GROUPS:
        sub = group_frames[group_key]
        binned = (
            sub.groupby("low_bac_bin", as_index=False)
            .agg(
                n=("event_id", "size"),
                recid_rate=("recidivism", "mean"),
                mean_bac=("low_bac", "mean"),
            )
            .rename(columns={"low_bac_bin": "bac_bin"})
        )
        binned["group"] = group_key
        binned["group_label"] = group_label
        rows.append(binned)
    return pd.concat(rows, ignore_index=True)


def fit_piecewise_lines(sub: pd.DataFrame) -> pd.DataFrame:
    segments = [
        (BAC_MIN, 0.079, "below_08"),
        (0.08, 0.15, "08_to_15"),
        (0.151, BAC_MAX, "above_15"),
    ]
    rows = []
    for low, high, label in segments:
        seg = sub[sub["low_bac"].between(low, high, inclusive="both")].copy()
        if len(seg) < 10:
            continue
        coef = np.polyfit(seg["low_bac"].to_numpy(), seg["recidivism"].to_numpy(), 1)
        x_vals = np.linspace(low, high, 100)
        y_vals = np.polyval(coef, x_vals)
        rows.append(
            pd.DataFrame(
                {
                    "segment": label,
                    "bac": x_vals,
                    "fit_rate": np.clip(y_vals, 0, 1),
                }
            )
        )
    if not rows:
        return pd.DataFrame(columns=["segment", "bac", "fit_rate"])
    return pd.concat(rows, ignore_index=True)


def plot_scatter_panels(sample: pd.DataFrame, binned: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.8), sharey=True)
    group_frames = {
        "overall": sample.copy(),
        "first_time": sample[sample["offense"].eq(1)].copy(),
        "repeat": sample[sample["offense"].ge(2)].copy(),
    }

    for ax, (group_key, group_label) in zip(axes, PLOT_GROUPS):
        sub = group_frames[group_key]
        bsub = binned[binned["group"] == group_key].copy()
        lines = fit_piecewise_lines(sub)

        for threshold in THRESHOLD_LINES:
            ax.axvline(threshold, color="#888888", linewidth=1.0, linestyle="--")

        if not lines.empty:
            for _, seg in lines.groupby("segment"):
                ax.plot(seg["bac"], seg["fit_rate"] * 100, color=LINE_COLOR, linewidth=1.5)

        ax.scatter(
            bsub["bac_bin"],
            bsub["recid_rate"] * 100,
            facecolors="none",
            edgecolors=SCATTER_COLOR,
            s=24,
            linewidths=1.0,
        )

        ax.set_xlim(BAC_MIN, BAC_MAX)
        ax.set_ylim(0, max(16, math.ceil(binned["recid_rate"].max() * 100 / 2) * 2 + 2))
        ax.set_xticks([0.05, 0.08, 0.10, 0.15, 0.20])
        ax.set_title(group_label)
        ax.set_xlabel("BAC")
        ax.grid(axis="y", color="#d9d9d9", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.text(
            0.031,
            ax.get_ylim()[1] - 0.7,
            f"N = {len(sub):,}\n3y recid = {sub['recidivism'].mean() * 100:.1f}%",
            ha="left",
            va="top",
            fontsize=9,
        )

    axes[0].set_ylabel("Future DUI within 3 years (%)")
    fig.suptitle("Contemporaneous BAC and 3-year future DUI", fontsize=15, y=1.02)
    fig.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, format="svg", bbox_inches="tight")
    plt.close(fig)


def first_nonblank(series: pd.Series) -> str:
    for value in series:
        if isinstance(value, str) and value.strip():
            return value
    return ""


def prepare_court_panel() -> pd.DataFrame:
    cols = [
        "doa",
        "dob",
        "offender_name",
        "license",
        "judge",
        "court_code",
        "chargenumber",
        "not_guilty",
        "guilty",
        "amended",
        "dismissed",
        "waiting",
        "deferred",
        "no_charges",
        "alcohol_assess",
        "monitor",
        "lic_surr",
        "victims_panel",
        "probation",
        "prob_length",
        "susp_length",
        "license_susp",
        "aa",
        "alcohol_treatment",
        "alcohol_school",
        "fine",
        "fine_held",
        "other_fine",
        "jail",
        "jail_held",
        "jail_sent",
        "phy_control",
        "under_age",
    ]
    frame = pd.read_stata(COURT_PATH, convert_categoricals=False, columns=cols)
    frame["doa_date"] = to_datetime_series(frame["doa"])
    frame["dob_date"] = to_datetime_series(frame["dob"])
    frame["license_norm"] = frame["license"].map(normalize_license)

    parsed = frame["offender_name"].map(parse_court_name)
    frame["court_name_norm"] = [item.full_name_norm for item in parsed]
    frame["last_name_norm"] = [item.last_name_norm for item in parsed]
    frame["first_name_norm"] = [item.first_name_norm for item in parsed]
    frame["first_initial"] = [item.first_initial for item in parsed]
    frame["middle_initial"] = [item.middle_initial for item in parsed]

    frame = frame[frame["doa_date"].notna() & frame["dob_date"].notna()].copy()

    numeric_cols = [
        "not_guilty",
        "guilty",
        "amended",
        "dismissed",
        "waiting",
        "deferred",
        "no_charges",
        "alcohol_assess",
        "monitor",
        "lic_surr",
        "victims_panel",
        "probation",
        "prob_length",
        "susp_length",
        "license_susp",
        "aa",
        "alcohol_treatment",
        "alcohol_school",
        "fine",
        "fine_held",
        "other_fine",
        "jail",
        "jail_held",
        "jail_sent",
        "phy_control",
        "under_age",
    ]
    for col in numeric_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)

    grouped = (
        frame.groupby(
            ["doa_date", "dob_date", "court_name_norm", "last_name_norm", "first_name_norm", "first_initial", "middle_initial"],
            as_index=False,
        )
        .agg(
            offender_name=("offender_name", "first"),
            license_norm=("license_norm", first_nonblank),
            judge=("judge", "first"),
            court_code=("court_code", "first"),
            chargenumber=("chargenumber", "first"),
            **{col: (col, "max") for col in numeric_cols},
        )
    )
    grouped["court_event_id"] = np.arange(len(grouped))
    return grouped


def make_date_candidates(
    breath: pd.DataFrame,
    court: pd.DataFrame,
    offsets: tuple[int, ...],
    dob_shifts: tuple[int, ...],
) -> pd.DataFrame:
    base_cols = [
        "event_id",
        "event_date",
        "dob_date",
        "subject_name_norm",
        "last_name_norm",
        "first_name_norm",
        "first_initial",
        "middle_initial",
        "license_norm",
        "low_bac",
        "recidivism",
        "offense",
        "year",
    ]
    breath_base = breath[base_cols].copy()
    candidate_frames = []

    for dob_shift in dob_shifts:
        temp = breath_base.copy()
        temp["dob_key"] = temp["dob_date"] + pd.to_timedelta(dob_shift, unit="D")
        temp["dob_diff"] = abs(dob_shift)
        for date_shift in offsets:
            shifted = temp.copy()
            shifted["date_key"] = shifted["event_date"] + pd.to_timedelta(date_shift, unit="D")
            merged = shifted.merge(
                court,
                left_on=["dob_key", "first_initial", "date_key"],
                right_on=["dob_date", "first_initial", "doa_date"],
                how="inner",
                suffixes=("_breath", "_court"),
            )
            if merged.empty:
                continue
            merged["date_diff"] = (merged["doa_date"] - merged["event_date"]).dt.days.abs()
            candidate_frames.append(merged)

    if not candidate_frames:
        return pd.DataFrame()
    candidates = pd.concat(candidate_frames, ignore_index=True)
    candidates = candidates.drop_duplicates(subset=["event_id", "court_event_id", "dob_diff", "date_diff"])
    return candidates


def score_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    candidates = candidates.copy()
    candidates["last_ratio"] = [
        safe_ratio(left, right)
        for left, right in zip(candidates["last_name_norm_breath"], candidates["last_name_norm_court"])
    ]
    candidates["first_ratio"] = [
        safe_ratio(left, right)
        for left, right in zip(candidates["first_name_norm_breath"], candidates["first_name_norm_court"])
    ]
    candidates["full_ratio"] = [
        safe_ratio(left, right)
        for left, right in zip(candidates["subject_name_norm"], candidates["court_name_norm"])
    ]
    candidates["license_exact"] = (
        candidates["license_norm_breath"].ne("")
        & candidates["license_norm_court"].ne("")
        & candidates["license_norm_breath"].eq(candidates["license_norm_court"])
    )
    candidates["middle_exact"] = candidates["middle_initial_breath"].eq(candidates["middle_initial_court"])

    candidates["score"] = (
        candidates["license_exact"].astype(int) * 30
        + candidates["last_ratio"] * 30
        + candidates["first_ratio"] * 15
        + candidates["full_ratio"] * 15
        + np.where(candidates["dob_diff"].eq(0), 12, np.where(candidates["dob_diff"].isin(DOB_SHIFT_DAYS), 6, 0))
        + np.where(candidates["middle_exact"], 3, 0)
        + np.where(candidates["date_diff"].eq(0), 10, np.where(candidates["date_diff"].eq(1), 6, 2))
    )

    keep = (
        candidates["license_exact"]
        | (
            (candidates["last_ratio"] >= 0.85)
            & (candidates["full_ratio"] >= 0.70)
            & (candidates["date_diff"] <= DATE_WINDOW_DAYS)
            & (candidates["dob_diff"].isin((0, 365, 366)))
        )
    )
    candidates = candidates[keep].copy()
    candidates["match_quality"] = np.where(
        candidates["score"] >= 85,
        "high",
        np.where(candidates["score"] >= 72, "medium", "low"),
    )
    return candidates


def pick_best_matches(breath: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        out = breath.copy()
        out["matched"] = False
        return out

    ranked = candidates.sort_values(
        ["event_id", "score", "license_exact", "last_ratio", "full_ratio", "date_diff", "dob_diff"],
        ascending=[True, False, False, False, False, True, True],
    ).copy()
    ranked["rank"] = ranked.groupby("event_id").cumcount() + 1
    best = ranked[ranked["rank"] == 1].copy()

    court_keep = [
        "court_event_id",
        "offender_name",
        "judge",
        "court_code",
        "chargenumber",
        "not_guilty",
        "guilty",
        "amended",
        "dismissed",
        "waiting",
        "deferred",
        "no_charges",
        "alcohol_assess",
        "monitor",
        "lic_surr",
        "victims_panel",
        "probation",
        "prob_length",
        "susp_length",
        "license_susp",
        "aa",
        "alcohol_treatment",
        "alcohol_school",
        "fine",
        "fine_held",
        "other_fine",
        "jail",
        "jail_held",
        "jail_sent",
        "phy_control",
        "under_age",
    ]

    keep_cols = [
        "event_id",
        "court_event_id",
        "score",
        "match_quality",
        "date_diff",
        "dob_diff",
        "last_ratio",
        "first_ratio",
        "full_ratio",
        "license_exact",
        *court_keep[1:],
    ]
    best = best[keep_cols]

    out = breath.merge(best, on="event_id", how="left")
    out["matched"] = out["court_event_id"].notna()
    return out


def build_match_summary(linked: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"metric": "adult_dui_events", "value": int(len(linked))},
        {"metric": "matched_events", "value": int(linked["matched"].sum())},
        {"metric": "match_rate", "value": float(linked["matched"].mean())},
        {"metric": "license_exact_rate_among_matches", "value": float(linked.loc[linked["matched"], "license_exact"].mean())},
        {"metric": "same_day_rate_among_matches", "value": float(linked.loc[linked["matched"], "date_diff"].eq(0).mean())},
        {"metric": "within_one_day_rate_among_matches", "value": float(linked.loc[linked["matched"], "date_diff"].le(1).mean())},
    ]

    by_year = (
        linked.groupby("year", as_index=False)
        .agg(events=("event_id", "size"), matched=("matched", "mean"))
        .rename(columns={"matched": "match_rate"})
    )
    by_year["metric"] = "match_rate_by_year"
    by_year["value"] = by_year["match_rate"]

    quality = (
        linked[linked["matched"]]
        .groupby("match_quality", as_index=False)
        .agg(matches=("event_id", "size"))
    )
    quality["metric"] = "matched_by_quality"
    quality["value"] = quality["matches"]

    summary = pd.DataFrame(rows)
    year_rows = by_year[["metric", "year", "events", "value"]]
    quality_rows = quality[["metric", "match_quality", "matches", "value"]]
    return pd.concat([summary, year_rows, quality_rows], ignore_index=True, sort=False)


def write_outputs(sample: pd.DataFrame, binned: pd.DataFrame, linked: pd.DataFrame, match_summary: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    binned.to_csv(OUT_BINNED, index=False)

    linked_out = linked[
        [
            "event_id",
            "event_date",
            "dob_date",
            "SubjectName",
            "License",
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
            "no_charges",
            "fine",
            "jail",
            "probation",
            "prob_length",
            "license_susp",
            "victims_panel",
            "alcohol_assess",
            "alcohol_treatment",
            "aa",
        ]
    ].copy()
    linked_out.to_csv(OUT_LINKED, index=False)
    match_summary.to_csv(OUT_MATCH_SUMMARY, index=False)

    overall = sample.copy()
    first = sample[sample["offense"].eq(1)].copy()
    repeat = sample[sample["offense"].ge(2)].copy()
    match_rate = linked["matched"].mean() * 100
    exact_license_rate = linked.loc[linked["matched"], "license_exact"].mean() * 100 if linked["matched"].any() else 0.0

    md = [
        "# Breath-test BAC, 3-year recidivism, and court linkage",
        "",
        "This package reproduces the older BAC-to-recidivism scatter using the saved `dui_analysis.dta` panel and then links those breath-test events to Washington court records using near-date and fuzzy-name matching.",
        "",
        "## BAC recidivism sample",
        "",
        f"- Source panel: `Older/dui_analysis.dta`",
        f"- Adult DUI events with BAC in [{BAC_MIN:.2f}, {BAC_MAX:.2f}] and full 3-year follow-up cohort ending in {FOLLOWUP_COHORT_END_YEAR}",
        f"- All offenders: `N = {len(overall):,}`, 3-year future DUI = `{overall['recidivism'].mean() * 100:.1f}%`",
        f"- First-time offenders: `N = {len(first):,}`, 3-year future DUI = `{first['recidivism'].mean() * 100:.1f}%`",
        f"- Repeat offenders: `N = {len(repeat):,}`, 3-year future DUI = `{repeat['recidivism'].mean() * 100:.1f}%`",
        "",
        f"![BAC and future DUI]({OUT_FIG.name})",
        "",
        "## Court linkage",
        "",
        f"- Breath-test side: adult DUI event rows from `dui_analysis.dta`",
        f"- Court side: `Older/punishments_offenders.dta`, aggregated to one court event per offender name / DOB / arrest date",
        f"- Blocking keys: first initial, DOB, and arrest date within +/-{DATE_WINDOW_DAYS} days",
        f"- Fuzzy scoring: last-name similarity, first-name similarity, full-name similarity, date proximity, and exact license bonus when available",
        f"- Match rate: `{match_rate:.1f}%` of adult DUI breath-test events",
        f"- Exact license agreement among matched events: `{exact_license_rate:.1f}%`",
        "",
        "## Files",
        "",
        f"- [bac_recidivism_three_panel.svg]({OUT_FIG.name})",
        f"- [bac_recidivism_binned.csv]({OUT_BINNED.name})",
        f"- [breath_to_court_linked_events.csv]({OUT_LINKED.name})",
        f"- [breath_to_court_match_summary.csv]({OUT_MATCH_SUMMARY.name})",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    breath = prepare_breath_panel()
    scatter_sample = prepare_scatter_sample(breath)
    binned = build_binned_summary(scatter_sample)
    plot_scatter_panels(scatter_sample, binned)

    court = prepare_court_panel()
    candidates = make_date_candidates(
        breath=breath,
        court=court,
        offsets=tuple(range(-DATE_WINDOW_DAYS, DATE_WINDOW_DAYS + 1)),
        dob_shifts=(0, *DOB_SHIFT_DAYS, *(-np.array(DOB_SHIFT_DAYS))),
    )
    scored = score_candidates(candidates)
    linked = pick_best_matches(breath, scored)
    match_summary = build_match_summary(linked)
    write_outputs(scatter_sample, binned, linked, match_summary)

    print(f"Wrote figure to {OUT_FIG}")
    print(f"Wrote binned BAC summary to {OUT_BINNED}")
    print(f"Wrote linked event file to {OUT_LINKED}")
    print(f"Wrote match summary to {OUT_MATCH_SUMMARY}")
    print(f"Wrote markdown summary to {OUT_MD}")


if __name__ == "__main__":
    main()
