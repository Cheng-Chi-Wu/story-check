"""Parse ETABS / SAP2000 table exports into a BuildingAnalysisInput dict (blueprint 5.1).

Three tables are needed, in any order and any file names; each is recognised by its columns:

  stories    Story | Height | Elevation(optional)
  drifts     Story | Output Case | Direction (or Item) | Max Drift | Avg Drift   ("Story Max Over Avg Drifts")
  stiffness  Story | Output Case | Stiff X | Stiff Y | Shear X/Y(optional)        ("Story Stiffness")

An Excel workbook may hold several of them, one per sheet. Values are converted to inches
and kips. Title rows above the header and the units row ETABS writes under it are skipped.

How output cases are used (a "row" is one story / case / step of the drift table)
  drift check      per story, envelope: the largest Max Drift and the largest Avg Drift over all
                   rows, each with its own case, so the governing value is never missed
  torsion (TIR)    per story, the largest Max/Avg ratio over all rows (cases and steps)
  soft story       one case per direction for the whole building: the case with the largest
                   story shear in that direction (or the largest stiffness if there is no shear)
  12.3.2.2 Exc. 1  every case that covers all stories; the checker claims the exception only if
                   it holds for each of them and reports the worst one
Every case used is recorded in project_info and printed in the report. Step Type "Min" rows
of the drift table are kept as magnitudes, since they can exceed the Max rows.

The column names follow the ETABS table names as best known; confirm them against real
exports from seed users and extend ALIASES rather than changing the logic.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

LENGTH_TO_IN = {"in": 1.0, "ft": 12.0, "mm": 1 / 25.4, "cm": 1 / 2.54, "m": 1 / 0.0254}
FORCE_TO_KIP = {"kip": 1.0, "kips": 1.0, "lb": 0.001, "kn": 1 / 4.4482216, "n": 1 / 4448.2216}

ALIASES = {
    "story": ("story", "name", "story name"),
    "height": ("height",),
    "elevation": ("elevation",),
    "case": ("output case", "load case/combo", "load case", "case"),
    "step_type": ("step type",),
    "step_number": ("step number", "step num"),
    "direction": ("direction",),
    "item": ("item",),
    "max_drift": ("max drift",),
    "avg_drift": ("avg drift",),
    "stiff_x": ("stiff x", "stiffness x"),
    "stiff_y": ("stiff y", "stiffness y"),
    "shear_x": ("shear x",),
    "shear_y": ("shear y",),
}

# Plausibility bounds used only for warnings, in inches.
STORY_HEIGHT_RANGE_IN = (72.0, 480.0)  # 6 ft to 40 ft
MAX_PLAUSIBLE_ELASTIC_DRIFT_RATIO = 0.05


def _rows_from_csv(source: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = source.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    # Text copied from an ETABS table grid (Ctrl+C) is tab-separated; exported CSV is comma-separated.
    delimiter = "\t" if text.count("\t") > text.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]  # title rows are shorter than the header


def _from_raw(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Find the header row (the first row with a story column) and return the table under it."""
    for i, row in raw.iterrows():
        cells = [str(c).strip().lower() if pd.notna(c) else "" for c in row]
        if any(c in ALIASES["story"] for c in cells):
            df = raw.iloc[i + 1 :].reset_index(drop=True)
            df.columns = cells
            df = df.loc[:, [c != "" for c in cells]]
            return _rename(df)
    return None


def read_tables(source, filename: str | None = None) -> list[pd.DataFrame]:
    """Read every table in a CSV / tab-separated text file or an Excel workbook (one table per sheet)."""
    if isinstance(source, (str, Path)):
        filename = filename or str(source)
        source = Path(source).read_bytes()
    elif not isinstance(source, bytes):
        source = source.read()
    label = filename or "table"

    if label.lower().endswith((".xlsx", ".xlsm", ".xls")):
        try:
            sheets = pd.read_excel(io.BytesIO(source), header=None, dtype=str, sheet_name=None)
        except Exception as e:  # noqa: BLE001 - surface any reader failure as a user message
            raise ValueError(f"{label}: could not be read as an Excel workbook ({e})") from None
        raws = list(sheets.values())
    else:
        raws = [pd.DataFrame(_rows_from_csv(source), dtype=str)]

    tables = [t for t in (_from_raw(r) for r in raws) if t is not None]
    if not tables:
        raise ValueError(f"{label}: no header row with a 'Story' column was found")
    return tables


def read_table(source, filename: str | None = None) -> pd.DataFrame:
    """Read a single table (the first one found)."""
    return read_tables(source, filename)[0]


def _rename(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for canonical, names in ALIASES.items():
        for name in names:
            if name in df.columns and canonical not in mapping.values():
                mapping[name] = canonical
    return df.rename(columns=mapping)


def identify(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if {"max_drift", "avg_drift"} <= cols:
        return "drifts"
    if {"stiff_x", "stiff_y"} <= cols:
        return "stiffness"
    if "height" in cols:
        return "stories"
    raise ValueError(f"unrecognised table with columns {sorted(map(str, cols))}")


def _numeric(df: pd.DataFrame, cols) -> pd.DataFrame:
    df = df.copy()
    df["story"] = df["story"].astype(str).str.strip()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=list(cols))


def _clean_case(df: pd.DataFrame, drop_min: bool) -> pd.DataFrame:
    if "case" in df.columns:
        df = df.assign(case=df["case"].astype(str).str.strip())
    if drop_min and "step_type" in df.columns:
        # Stiffness: the Min row of a response-spectrum case is not a design quantity.
        df = df[df["step_type"].astype(str).str.strip().str.lower() != "min"]
    return df


def _row_labels(df: pd.DataFrame) -> pd.Series | None:
    """Case name per row, with the step when a case has several steps, e.g. 'EQX step 2' or 'RSX (Min)'."""
    if "case" not in df.columns:
        return None
    label = df["case"].copy()
    if "step_number" in df.columns:
        step = df["step_number"].astype(str).str.strip()
        multi = df.groupby("case")["step_number"].transform("nunique") > 1
        label = label.where(~multi, label + " step " + step)
    if "step_type" in df.columns:
        is_min = df["step_type"].astype(str).str.strip().str.lower() == "min"
        label = label.where(~is_min, label + " (Min)")
    return label


def _filter_case(df: pd.DataFrame, case: str | None, table: str) -> pd.DataFrame:
    if not case:
        return df
    if "case" not in df.columns:
        raise ValueError(f"{table} table has no output case column to filter on")
    out = df[df["case"].str.lower() == case.strip().lower()]
    if out.empty:
        raise ValueError(f"output case {case!r} not found in the {table} table")
    return out


def _parse_stories(df: pd.DataFrame, length: float) -> pd.DataFrame:
    has_elevation = "elevation" in df.columns
    df = _numeric(df, ["height", "elevation"] if has_elevation else ["height"])
    df = df[df["height"] > 0]  # drops the "Base" row
    if not has_elevation:
        # ETABS lists stories top-down; accumulate heights from the bottom.
        df = df.iloc[::-1].copy()
        df["elevation"] = df["height"].cumsum()
    df = df.sort_values("elevation")
    out = pd.DataFrame({"height_in": df["height"] * length, "elevation_in": df["elevation"] * length})
    out.index = df["story"]
    return out


def _directions(df: pd.DataFrame) -> pd.Series:
    if "direction" in df.columns:
        return df["direction"].astype(str).str.strip().str.upper()
    if "item" in df.columns:  # e.g. "Diaph D1 X"
        return df["item"].astype(str).str.extract(r"\b([XYxy])\s*$", expand=False).str.upper()
    raise ValueError("drift table has no Direction column")


def _parse_drifts(df: pd.DataFrame, length: float, case_x, case_y, warnings: list):
    """Returns (per-story drift table, case record, directions that have data)."""
    df = _clean_case(_numeric(df, ["max_drift", "avg_drift"]), drop_min=False)
    df = df.assign(direction=_directions(df))
    negative = int((df[["max_drift", "avg_drift"]] < 0).sum().sum())
    if negative:
        warnings.append(
            f"{negative} negative drift value(s) were converted to absolute values. The Story Max Over Avg "
            "Drifts table normally holds magnitudes; check that the right table was exported."
        )
    df[["max_drift", "avg_drift"]] = df[["max_drift", "avg_drift"]].abs() * length
    labels = _row_labels(df)
    df = df.assign(label=labels if labels is not None else None)
    has_case = labels is not None

    # Validate every row, not only the governing ones.
    for _, r in df.iterrows():
        where = f"{r['story']}, {r['direction']}" + (f", {r['label']}" if has_case else "")
        if r["avg_drift"] <= 0 < r["max_drift"]:
            raise ValueError(f"drift table row ({where}): Avg Drift is zero while Max Drift is not")
        if r["max_drift"] < r["avg_drift"] * (1 - 1e-3) - 1e-9:
            raise ValueError(f"drift table row ({where}): Max Drift is smaller than Avg Drift")

    parts, record, present = {}, {"drift": {}, "torsion": {}, "exception": {}}, []
    for d, case in (("x", case_x), ("y", case_y)):
        rows = df[df["direction"] == d.upper()]
        if rows.empty:
            continue  # one-direction exports are allowed; that direction is reported as N/A
        rows = _filter_case(rows, case, "drift")
        present.append(d)
        by_story = rows.groupby("story")

        # Drift check: envelope of max and of avg separately, each with its own governing row.
        g_max = rows.loc[by_story["max_drift"].idxmax()].set_index("story")
        g_avg = rows.loc[by_story["avg_drift"].idxmax()].set_index("story")
        parts[f"max_drift_{d}_in"] = g_max["max_drift"]
        parts[f"avg_drift_{d}_in"] = g_avg["avg_drift"]

        # Torsion: the largest TIR over every row; it may come from a case with smaller drifts.
        pos = rows[rows["avg_drift"] > 0].assign(tir=lambda r: r["max_drift"] / r["avg_drift"])
        if not pos.empty:
            t = pos.loc[pos.groupby("story")["tir"].idxmax()].set_index("story")
            parts[f"tir_{d}"] = t["tir"]
            if has_case:
                parts[f"tir_{d}_case"] = t["label"]
                record["torsion"][d] = sorted(t["label"].unique())
        if not has_case:
            continue
        parts[f"drift_max_{d}_case"] = g_max["label"]
        parts[f"drift_{d}_case"] = g_avg["label"]
        record["drift"][d] = sorted(set(g_max["label"]) | set(g_avg["label"]))

        # Exception 1 compares neighbouring stories, so each case is kept as one whole-building profile.
        n_stories = rows["story"].nunique()
        full = [c for c, g in rows.groupby("label") if g["story"].nunique() == n_stories]
        profiles = {c: rows[rows["label"] == c].groupby("story")["avg_drift"].max() for c in full}
        parts[f"exc_drifts_{d}"] = pd.Series(
            {st: {c: round(float(p[st]), 6) for c, p in profiles.items()} for st in rows["story"].unique()}
        )
        record["exception"][d] = full
        if not full:
            warnings.append(
                f"No {d.upper()}-direction output case covers every story, so 12.3.2.2 Exception 1 is not evaluated."
            )
    if not present:
        raise ValueError("drift table has no rows for direction X or Y; check the Direction column")
    return pd.DataFrame(parts), record, present


def _parse_stiffness(df: pd.DataFrame, length: float, force: float, case_x, case_y, directions):
    """One output case per direction for the whole building. Returns (table, {direction: case})."""
    df = _clean_case(_numeric(df, ["stiff_x", "stiff_y"]), drop_min=True)
    parts, used = {}, {}
    for d, case in (("x", case_x), ("y", case_y)):
        if d not in directions:
            continue
        rows = _filter_case(df, case, "stiffness")
        stiff, shear = f"stiff_{d}", f"shear_{d}"
        if "case" in rows.columns and rows["case"].nunique() > 1:
            if shear in rows.columns:
                size = pd.to_numeric(rows[shear], errors="coerce").abs().groupby(rows["case"]).max()
            else:
                size = rows[stiff].abs().groupby(rows["case"]).sum()
            best = size.idxmax()
            rows = rows[rows["case"] == best]
            used[d] = best
        elif "case" in rows.columns and not rows.empty:
            used[d] = rows["case"].iloc[0]
        gov = rows.groupby("story")[stiff].max()
        parts[f"stiffness_{d}_kip_in"] = gov * force / length
        if d in used:
            parts[f"stiffness_{d}_case"] = pd.Series(used[d], index=gov.index)
    return pd.DataFrame(parts), used


def _plausibility(merged: pd.DataFrame, directions, warnings: list):
    for d in directions:
        zero = merged.index[merged[f"max_drift_{d}_in"] <= 0].tolist()
        if zero:
            warnings.append(
                f"Zero {d.upper()}-direction drift at {', '.join(zero)}; a story above the base should move. "
                "Check the export. The drift check for these stories is reported as N/A."
            )
    lo, hi = merged["height_in"].min(), merged["height_in"].max()
    if lo < STORY_HEIGHT_RANGE_IN[0] or hi > STORY_HEIGHT_RANGE_IN[1]:
        warnings.append(
            f"Story heights range from {lo / 12:.1f} ft to {hi / 12:.1f} ft after unit conversion; "
            "check that the length unit matches the files."
        )
    ratio = (merged[[f"avg_drift_{d}_in" for d in directions]].max(axis=1) / merged["height_in"]).max()
    if ratio > MAX_PLAUSIBLE_ELASTIC_DRIFT_RATIO:
        warnings.append(
            f"The largest drift / height ratio in the files is {ratio:.3f}, which is unusually large; "
            "check the length unit and the selected output cases."
        )


def parse_etabs(
    tables,
    project_info: dict,
    length_unit: str = "in",
    force_unit: str = "kip",
    case_x: str | None = None,
    case_y: str | None = None,
) -> dict:
    """Build a BuildingAnalysisInput from the three ETABS tables.

    tables       iterable of DataFrames from read_tables(), or of file paths
    case_x/y     output case to use per direction; default is described in the module docstring
    """
    try:
        length = LENGTH_TO_IN[length_unit.lower()]
        force = FORCE_TO_KIP[force_unit.lower()]
    except KeyError as e:
        raise ValueError(f"unsupported unit {e.args[0]!r}") from None

    found = {}
    for t in tables:
        for df in [t] if isinstance(t, pd.DataFrame) else read_tables(t):
            kind = identify(df)
            if kind in found:
                raise ValueError(f"two {kind} tables were provided")
            found[kind] = df
    missing = {"stories", "drifts", "stiffness"} - set(found)
    if missing:
        raise ValueError(f"missing table(s): {', '.join(sorted(missing))}")

    warnings: list[str] = []
    stories = _parse_stories(found["stories"], length)
    if stories.empty:
        raise ValueError("no stories found")
    drifts, record, directions = _parse_drifts(found["drifts"], length, case_x, case_y, warnings)
    stiffness, stiff_cases = _parse_stiffness(found["stiffness"], length, force, case_x, case_y, directions)

    merged = stories.join(drifts).join(stiffness)
    problems = []
    for name, row in merged.iterrows():
        lacking = [
            label
            for label, cols in (
                ("drift", [f"max_drift_{d}_in" for d in directions]),
                ("stiffness", [f"stiffness_{d}_kip_in" for d in directions]),
            )
            if row[cols].isna().any()
        ]
        if lacking:
            problems.append(f"{name} (no {' or '.join(lacking)} row)")
    if problems:
        raise ValueError(
            "stories in Story Definitions without matching rows in the other tables: " + ", ".join(problems)
        )
    _plausibility(merged, directions, warnings)

    info = dict(project_info)
    info["units"] = {"length": "in", "force": "kips"}
    if record["drift"]:
        info["drift_output_cases"] = record["drift"]
    if record["torsion"]:
        info["torsion_output_cases"] = record["torsion"]
    if any(record["exception"].values()):
        info["exception_output_cases"] = {d: c for d, c in record["exception"].items() if c}
    if stiff_cases:
        info["stiffness_output_case"] = stiff_cases
    missing = [d.upper() for d in ("x", "y") if d not in directions]
    if missing:
        warnings.append(
            f"The drift table has no {' or '.join(missing)}-direction rows; those checks are reported as N/A."
        )
    if warnings:
        info["input_warnings"] = warnings

    def value(v):
        return v if isinstance(v, (str, dict)) else round(float(v), 6)

    def fields(row):
        # Case names stay strings, exception profiles stay dicts; optional columns may be missing per story.
        return {k: value(v) for k, v in row.items() if isinstance(v, (str, dict)) or pd.notna(v)}

    return {
        "project_info": info,
        "stories": [{"story_name": name, **fields(row)} for name, row in merged.iterrows()],
    }
