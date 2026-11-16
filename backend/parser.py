"""Parse ETABS / SAP2000 table exports into a BuildingAnalysisInput dict (blueprint 5.1).

Three tables are needed, in any order and any file names; each is recognised by its columns:

  stories    Story | Height | Elevation(optional)
  drifts     Story | Output Case | Direction | Max Drift | Avg Drift      ("Story Max Over Avg Drifts")
  stiffness  Story | Output Case | Stiff X | Stiff Y                      ("Story Stiffness")

Values are converted to inches and kips. Rows that are not numeric (such as the units
row ETABS writes under the header) are dropped.

The column names follow the ETABS table names as best known; confirm them against real
exports from seed users and extend ALIASES rather than changing the logic.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

LENGTH_TO_IN = {"in": 1.0, "ft": 12.0, "mm": 1 / 25.4, "cm": 1 / 2.54, "m": 1 / 0.0254}
FORCE_TO_KIP = {"kip": 1.0, "kips": 1.0, "lb": 0.001, "kn": 1 / 4.4482216, "n": 1 / 4448.2216}

ALIASES = {
    "story": ("story", "name", "story name"),
    "height": ("height",),
    "elevation": ("elevation",),
    "case": ("output case", "load case/combo", "load case", "case"),
    "direction": ("direction",),
    "max_drift": ("max drift",),
    "avg_drift": ("avg drift",),
    "stiff_x": ("stiff x", "stiffness x"),
    "stiff_y": ("stiff y", "stiffness y"),
    "shear_x": ("shear x",),
    "shear_y": ("shear y",),
}


def read_table(source, filename: str | None = None) -> pd.DataFrame:
    """Read a CSV or Excel export. `source` is a path, bytes, or a binary file object."""
    if isinstance(source, (str, Path)):
        filename = filename or str(source)
        source = Path(source).read_bytes()
    elif not isinstance(source, bytes):
        source = source.read()

    if (filename or "").lower().endswith((".xlsx", ".xlsm", ".xls")):
        raw = pd.read_excel(io.BytesIO(source), header=None, dtype=str)
    else:
        raw = pd.read_csv(io.BytesIO(source), header=None, dtype=str, skip_blank_lines=True)

    # The header is the first row that has a story column; ETABS Excel exports put a title row above it.
    for i, row in raw.iterrows():
        cells = [str(c).strip().lower() for c in row]
        if any(c in ALIASES["story"] for c in cells):
            df = raw.iloc[i + 1 :].reset_index(drop=True)
            df.columns = cells
            return _rename(df)
    raise ValueError(f"{filename or 'table'}: no header row with a 'Story' column was found")


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


def _filter_case(df: pd.DataFrame, case: str | None, table: str) -> pd.DataFrame:
    if not case:
        return df
    if "case" not in df.columns:
        raise ValueError(f"{table} table has no output case column to filter on")
    out = df[df["case"].astype(str).str.strip().str.lower() == case.strip().lower()]
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
    out = pd.DataFrame(
        {"height_in": df["height"] * length, "elevation_in": df["elevation"] * length}
    )
    out.index = df["story"]
    return out


def _parse_drifts(df: pd.DataFrame, length: float, case_x, case_y):
    """Returns (drift table, {direction: output cases the governing rows came from}).""" 
    df = _numeric(df, ["max_drift", "avg_drift"])
    if "direction" not in df.columns:
        raise ValueError("drift table has no Direction column")
    df["direction"] = df["direction"].astype(str).str.strip().str.upper()
    df[["max_drift", "avg_drift"]] = df[["max_drift", "avg_drift"]].abs() * length

    parts, cases = {}, {}
    for d, case in (("x", case_x), ("y", case_y)):
        rows = _filter_case(df[df["direction"] == d.upper()], case, "drift")
        if rows.empty:
            raise ValueError(f"drift table has no rows for direction {d.upper()}")
        # One row per story: the governing (largest max drift) row of the selected cases.
        gov = rows.loc[rows.groupby("story")["max_drift"].idxmax()].set_index("story")
        parts[f"max_drift_{d}_in"] = gov["max_drift"]
        parts[f"avg_drift_{d}_in"] = gov["avg_drift"]
        if "case" in gov.columns:
            cases[d] = sorted(gov["case"].astype(str).str.strip().unique())
    return pd.DataFrame(parts), cases


def _parse_stiffness(df: pd.DataFrame, length: float, force: float, case_x, case_y) -> pd.DataFrame:
    df = _numeric(df, ["stiff_x", "stiff_y"])
    parts = {}
    for d, case in (("x", case_x), ("y", case_y)):
        rows = _filter_case(df, case, "stiffness")
        rows = rows[rows[f"stiff_{d}"] > 0]
        shear = f"shear_{d}"
        if shear in rows.columns:
            # Take the case that loads this direction hardest, i.e. the largest story shear.
            rows = rows.assign(**{shear: pd.to_numeric(rows[shear], errors="coerce").abs().fillna(0)})
            gov = rows.loc[rows.groupby("story")[shear].idxmax()].set_index("story")[f"stiff_{d}"]
        else:
            gov = rows.groupby("story")[f"stiff_{d}"].max()
        parts[f"stiffness_{d}_kip_in"] = gov * force / length
    return pd.DataFrame(parts)


def parse_etabs(
    tables,
    project_info: dict,
    length_unit: str = "in",
    force_unit: str = "kip",
    case_x: str | None = None,
    case_y: str | None = None,
) -> dict:
    """Build a BuildingAnalysisInput from the three ETABS tables.

    tables       iterable of DataFrames from read_table(), or of file paths
    case_x/y     output case to use per direction; default is the governing case per story
    """
    try:
        length = LENGTH_TO_IN[length_unit.lower()]
        force = FORCE_TO_KIP[force_unit.lower()]
    except KeyError as e:
        raise ValueError(f"unsupported unit {e.args[0]!r}") from None

    found = {}
    for t in tables:
        df = t if isinstance(t, pd.DataFrame) else read_table(t)
        kind = identify(df)
        if kind in found:
            raise ValueError(f"two {kind} tables were provided")
        found[kind] = df
    missing = {"stories", "drifts", "stiffness"} - set(found)
    if missing:
        raise ValueError(f"missing table(s): {', '.join(sorted(missing))}")

    stories = _parse_stories(found["stories"], length)
    drifts, cases = _parse_drifts(found["drifts"], length, case_x, case_y)
    stiffness = _parse_stiffness(found["stiffness"], length, force, case_x, case_y)

    merged = stories.join(drifts).join(stiffness)
    incomplete = merged[merged.isna().any(axis=1)].index.tolist()
    if incomplete:
        raise ValueError(f"stories missing drift or stiffness data: {', '.join(incomplete)}")
    if merged.empty:
        raise ValueError("no stories found")

    info = dict(project_info)
    info["units"] = {"length": "in", "force": "kips"}
    if cases:
        info["drift_output_cases"] = cases  # shown in the report so the reviewer knows the source
    return {
        "project_info": info,
        "stories": [
            {"story_name": name, **{k: round(float(v), 6) for k, v in row.items()}}
            for name, row in merged.iterrows()
        ],
    }
