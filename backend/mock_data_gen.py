"""Generate mock ETABS exports for three buildings with deliberately planted violations.

    python -m backend.mock_data_gen          # writes into ./data/<building>/

Each building folder holds the three tables the parser expects plus project.json
(the project_info to send along). Output is deterministic.

Planted conditions
  05_story_office     SDC D  torsional irregularity Type 1a at Story 2 (X)             -> WARNING
  15_story_tower      SDC D  extreme soft story at Story 1 pushing drift over the limit,
                             extreme torsion Type 1b at Story 4 (X)                    -> FAIL (drift)
  30_story_highrise   SDC E  extreme soft story at Story 12, extreme torsion at
                             Story 20 (Y); both prohibited in SDC E                    -> FAIL
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

IMPORTANCE = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}

BUILDINGS = [
    {
        "folder": "05_story_office",
        "n": 5,
        "target_drift_ratio": 0.012,
        "project_info": {
            "building_name": "Pasadena 5-Story Office",
            "risk_category": "II",
            "seismic_design_category": "D",
            "structure_type": "other",
            "cd": 5.5,
        },
        "torsion": {(2, "x"): 1.30},
        "soft": {},
    },
    {
        "folder": "15_story_tower",
        "n": 15,
        "target_drift_ratio": 0.013,
        "project_info": {
            "building_name": "Los Angeles 15-Story Commercial Tower",
            "risk_category": "II",
            "seismic_design_category": "D",
            "structure_type": "other",
            "cd": 5.5,
        },
        "torsion": {(4, "x"): 1.50},
        "soft": {1: 0.50},
    },
    {
        "folder": "30_story_highrise",
        "n": 30,
        "target_drift_ratio": 0.009,
        "project_info": {
            "building_name": "San Francisco 30-Story High-Rise",
            "risk_category": "III",
            "seismic_design_category": "E",
            "structure_type": "other",
            "cd": 5.5,
        },
        "torsion": {(20, "y"): 1.55},
        "soft": {12: 0.55},
    },
]


def generate(spec: dict) -> dict[str, pd.DataFrame]:
    """Return the three ETABS-style tables (stories listed top-down, inches and kips)."""
    n = spec["n"]
    info = spec["project_info"]
    amplification = info["cd"] / IMPORTANCE[info["risk_category"]]
    base_shear = 220.0 * n  # kips

    heights = [180.0] + [156.0] * (n - 1)
    elevations = [sum(heights[: i + 1]) for i in range(n)]

    # Smooth elastic profile: shear and stiffness both reduce with height.
    shear = [1.0 - (i / n) ** 2 for i in range(n)]
    stiff = [1.0 - 0.6 * i / n for i in range(n)]
    shape = [shear[i] / stiff[i] / heights[i] for i in range(n)]  # relative drift ratio
    scale = spec["target_drift_ratio"] / amplification / max(shape)

    story_rows, drift_rows, stiff_rows = [], [], []
    for i in reversed(range(n)):
        number = i + 1
        name = f"Story{number}"
        story_rows.append({"Story": name, "Height": heights[i], "Elevation": elevations[i]})

        v = base_shear * shear[i]
        for d, k_factor, base_ratio in (("x", 1.0, 1.08), ("y", 1.15, 1.05)):
            avg = shape[i] * scale * heights[i] / k_factor
            avg /= spec["soft"].get(number, 1.0)  # a softer story drifts more under the same shear
            ratio = spec["torsion"].get((number, d), base_ratio)
            case = f"EQ{d.upper()}"
            drift_rows.append(
                {
                    "Story": name,
                    "Output Case": case,
                    "Case Type": "LinStatic",
                    "Direction": d.upper(),
                    "Max Drift": round(avg * ratio, 5),
                    "Avg Drift": round(avg, 5),
                    "Ratio": round(ratio, 3),
                }
            )
            row = {"Story": name, "Output Case": case, "Case Type": "LinStatic"}
            for other in ("X", "Y"):
                active = other == d.upper()
                row[f"Shear {other}"] = round(v, 2) if active else 0.0
                row[f"Drift {other}"] = round(avg, 5) if active else 0.0
                row[f"Stiff {other}"] = round(v / avg, 2) if active else 0.0
            stiff_rows.append(row)

    story_rows.append({"Story": "Base", "Height": 0.0, "Elevation": 0.0})
    return {
        "story_definitions": pd.DataFrame(story_rows),
        "story_max_over_avg_drifts": pd.DataFrame(drift_rows),
        "story_stiffness": pd.DataFrame(stiff_rows),
    }


def write_all(root: str | Path = "data") -> list[Path]:
    folders = []
    for spec in BUILDINGS:
        folder = Path(root) / spec["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        for name, df in generate(spec).items():
            df.to_csv(folder / f"{name}.csv", index=False)
        (folder / "project.json").write_text(json.dumps(spec["project_info"], indent=2) + "\n")
        folders.append(folder)
    return folders


if __name__ == "__main__":
    for path in write_all():
        print(f"wrote {path}")
