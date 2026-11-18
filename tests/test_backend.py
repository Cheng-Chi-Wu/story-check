"""Parser, mock data, API and report tests. Run from the repo root: python -m pytest"""

import io
import json

import pandas as pd
import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.code_checker import check_building
from backend.main import app
from backend.mock_data_gen import BUILDINGS, write_all
from backend.parser import parse_etabs, read_table

client = TestClient(app)


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    write_all(root)
    return root


def load(data, folder):
    path = data / folder
    info = json.loads((path / "project.json").read_text())
    return parse_etabs(sorted(path.glob("*.csv")), info)


def flagged(result):
    return {
        (s["story_name"], c["check_type"], c["status"])
        for s in result["story_results"]
        for c in s["checks"]
        if c["status"] != "PASS"
    }


# ---------- Parser ----------


@pytest.mark.parametrize("spec", BUILDINGS, ids=lambda s: s["folder"])
def test_parser_output_shape(data, spec):
    b = load(data, spec["folder"])
    assert len(b["stories"]) == spec["n"]  # Base row dropped
    assert b["project_info"]["units"] == {"length": "in", "force": "kips"}
    elevations = [s["elevation_in"] for s in b["stories"]]
    assert elevations == sorted(elevations)
    assert b["stories"][0]["story_name"] == "Story1"
    assert b["stories"][0]["height_in"] == 180.0
    assert all(s["stiffness_x_kip_in"] > 0 and s["stiffness_y_kip_in"] > 0 for s in b["stories"])


def tables(stories, drifts, stiffness):
    return [pd.DataFrame(stories), pd.DataFrame(drifts), pd.DataFrame(stiffness)]


def csv_table(df):
    return read_table(df.to_csv(index=False).encode(), "t.csv")


def simple_tables(length=1.0, force=1.0):
    stories = [{"Story": "S2", "Height": 144 * length}, {"Story": "S1", "Height": 180 * length}]
    drifts = [
        {"Story": s, "Output Case": "EQ" + d, "Direction": d, "Max Drift": 0.33 * length, "Avg Drift": 0.30 * length}
        for s in ("S2", "S1")
        for d in ("X", "Y")
    ]
    k = 1000.0 * force / length
    stiffness = [{"Story": s, "Output Case": "EQX", "Stiff X": k, "Stiff Y": k} for s in ("S2", "S1")]
    return [csv_table(t) for t in tables(stories, drifts, stiffness)]


def test_elevation_is_accumulated_when_missing():
    b = parse_etabs(simple_tables(), {"risk_category": "II"})
    assert [(s["story_name"], s["elevation_in"]) for s in b["stories"]] == [("S1", 180.0), ("S2", 324.0)]


def test_unit_conversion_mm_kn():
    b = parse_etabs(simple_tables(length=25.4, force=4.4482216), {"risk_category": "II"}, "mm", "kN")
    s1 = b["stories"][0]
    assert s1["height_in"] == pytest.approx(180.0)
    assert s1["max_drift_x_in"] == pytest.approx(0.33)
    assert s1["stiffness_x_kip_in"] == pytest.approx(1000.0)


def test_units_row_and_title_row_are_skipped():
    text = "TABLE: Story Definitions,,\nStory,Height,Elevation\n,in,in\nS2,144,324\nS1,180,180\nBase,0,0\n"
    df = read_table(text.encode(), "stories.csv")
    assert list(df.columns) == ["story", "height", "elevation"]
    others = simple_tables()[1:]
    assert len(parse_etabs([df, *others], {"risk_category": "II"})["stories"]) == 2


def test_governing_case_and_case_filter():
    t = simple_tables()
    extra = pd.DataFrame(
        [{"story": "S1", "case": "RSX", "direction": "X", "max_drift": "0.50", "avg_drift": "0.40"}]
    )
    t[1] = pd.concat([t[1], extra], ignore_index=True)
    assert parse_etabs(t, {"risk_category": "II"})["stories"][0]["max_drift_x_in"] == 0.50
    assert parse_etabs(t, {"risk_category": "II"}, case_x="EQX")["stories"][0]["max_drift_x_in"] == 0.33
    with pytest.raises(ValueError, match="not found"):
        parse_etabs(t, {"risk_category": "II"}, case_x="NOPE")


def test_single_field_title_line_is_skipped():
    # A title line with one field used to crash the CSV tokenizer (reviewer finding).
    text = "TABLE:  Story Max Over Avg Drifts\nStory,Output Case,Direction,Max Drift,Avg Drift\nS2,EQX,X,0.33,0.30\n"
    df = read_table(text.encode(), "drifts.csv")
    assert {"story", "case", "direction", "max_drift", "avg_drift"} <= set(df.columns)


def test_tir_is_the_largest_over_cases_not_the_largest_drift_case():
    t = simple_tables()
    extra = pd.DataFrame([{"story": "S1", "case": "EQX-Ecc", "direction": "X", "max_drift": "0.30", "avg_drift": "0.15"}])
    t[1] = pd.concat([t[1], extra], ignore_index=True)
    b = parse_etabs(t, {"risk_category": "II"})
    s1 = b["stories"][0]
    assert s1["max_drift_x_in"] == 0.33 and s1["drift_x_case"] == "EQX"
    assert s1["tir_x"] == pytest.approx(2.0) and s1["tir_x_case"] == "EQX-Ecc"
    b["project_info"]["drift_is_amplified"] = True
    torsion = next(c for c in check_building(b)["story_results"][0]["checks"] if c["check_type"].startswith("Torsional Irregularity (X"))
    assert torsion["status"] == "WARNING" and torsion["demand_value"] == pytest.approx(2.0)


def test_step_type_min_rows_and_item_direction():
    t = simple_tables()
    drifts = t[1].drop(columns=["direction"]).assign(item=lambda d: "Diaph D1 " + d["case"].str[-1], step_type="Max")
    mins = drifts.assign(step_type="Min", max_drift="-9.9", avg_drift="-9.0")
    t[1] = pd.concat([drifts, mins], ignore_index=True)
    s1 = parse_etabs(t, {"risk_category": "II"})["stories"][0]
    # Codex N3: a Min row larger in magnitude than the Max row governs.
    assert s1["max_drift_x_in"] == 9.9 and s1["avg_drift_y_in"] == 9.0
    assert s1["drift_x_case"].endswith("(Min)")


def test_excel_workbook_with_all_tables_on_separate_sheets():
    from backend.parser import read_tables

    stories = pd.DataFrame([{"Story": "S2", "Height": 144}, {"Story": "S1", "Height": 180}])
    drifts = pd.DataFrame(
        [{"Story": s, "Output Case": "EQ" + d, "Direction": d, "Max Drift": 0.33, "Avg Drift": 0.30} for s in ("S2", "S1") for d in "XY"]
    )
    stiff = pd.DataFrame([{"Story": s, "Output Case": "EQX", "Stiff X": 1000, "Stiff Y": 1000} for s in ("S2", "S1")])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xl:
        for name, df in (("Stories", stories), ("Drifts", drifts), ("Stiffness", stiff)):
            df.to_excel(xl, sheet_name=name, index=False)
    found = read_tables(buf.getvalue(), "all.xlsx")
    assert len(found) == 3
    assert len(parse_etabs(found, {"risk_category": "II"})["stories"]) == 2


def test_negative_drifts_and_wrong_unit_produce_warnings():
    t = simple_tables()
    t[1] = t[1].assign(max_drift=lambda d: "-" + d["max_drift"], avg_drift=lambda d: "-" + d["avg_drift"])
    info = parse_etabs(t, {"risk_category": "II"})["project_info"]
    assert any("negative drift" in w for w in info["input_warnings"])
    info = parse_etabs(simple_tables(), {"risk_category": "II"}, length_unit="ft")["project_info"]
    assert any("length unit" in w for w in info["input_warnings"])
    assert "input_warnings" not in parse_etabs(simple_tables(), {"risk_category": "II"})["project_info"]


def test_stiffness_uses_one_case_for_the_whole_building():
    t = simple_tables()
    stiff = pd.DataFrame(
        [{"story": s, "case": c, "stiff_x": k, "stiff_y": "0", "shear_x": v}
         for s, c, k, v in (("S1", "EQX", "1000", "500"), ("S2", "EQX", "1000", "300"),
                            ("S1", "RSX", "4000", "200"), ("S2", "RSX", "9000", "150"))]
    )
    t[2] = stiff
    b = parse_etabs(t, {"risk_category": "II"})
    assert [s["stiffness_x_kip_in"] for s in b["stories"]] == [1000.0, 1000.0]
    assert b["project_info"]["stiffness_output_case"]["x"] == "EQX"


def test_parser_errors():
    t = simple_tables()
    with pytest.raises(ValueError, match="missing table"):
        parse_etabs(t[:2], {})
    with pytest.raises(ValueError, match="two drifts"):
        parse_etabs([t[0], t[1], t[1]], {})
    with pytest.raises(ValueError, match="unsupported unit"):
        parse_etabs(t, {}, length_unit="furlong")
    with pytest.raises(ValueError, match="no header row"):
        read_table(b"a,b\n1,2\n", "x.csv")
    t[1] = t[1][t[1]["story"] != "S1"]
    with pytest.raises(ValueError, match=r"S1 \(no drift row\)"):
        parse_etabs(t, {})


# ---------- Mock buildings carry the planted violations ----------


def test_mock_05_story(data):
    r = check_building(load(data, "05_story_office"))
    assert r["summary"]["overall_status"] == "WARNING"
    assert flagged(r) == {("Story2", "Torsional Irregularity (X-Dir)", "WARNING")}


def test_mock_15_story(data):
    r = check_building(load(data, "15_story_tower"))
    assert r["summary"]["overall_status"] == "FAIL"
    assert flagged(r) == {
        ("Story1", "Soft Story Irregularity (X-Dir)", "WARNING"),
        ("Story1", "Soft Story Irregularity (Y-Dir)", "WARNING"),
        ("Story1", "Allowable Story Drift (X-Dir)", "FAIL"),
        ("Story4", "Torsional Irregularity (X-Dir)", "WARNING"),
    }


def test_mock_30_story(data):
    r = check_building(load(data, "30_story_highrise"))
    assert r["summary"]["overall_status"] == "FAIL"
    f = flagged(r)
    assert ("Story12", "Soft Story Irregularity (X-Dir)", "FAIL") in f
    # ASCE 7-22: a large TIR is an irregularity with consequences, not a prohibition
    assert ("Story20", "Torsional Irregularity (Y-Dir)", "WARNING") in f
    assert {name for name, _, _ in f} == {"Story12", "Story20"}


# ---------- API ----------


def post_analyze(data, folder, **form):
    path = data / folder
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(path.glob("*.csv"))]
    form.setdefault("project_info", (path / "project.json").read_text())
    return client.post("/api/analyze", files=files, data=form)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_analyze_end_to_end(data):
    resp = post_analyze(data, "15_story_tower")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["total_stories"] == 15
    assert body["summary"]["overall_status"] == "FAIL"
    assert body["project_info"]["seismic_design_category"] == "D"
    assert body == {**check_building(load(data, "15_story_tower")), "project_info": body["project_info"]}


@pytest.mark.parametrize(
    "project_info, message",
    [
        ("{not json", "not valid JSON"),
        ("[]", "must be a JSON object"),
        ('{"risk_category": "II"}', "cd is required"),
        ('{"risk_category": "IX", "cd": 5.5}', "risk_category"),
    ],
)
def test_analyze_rejects_bad_project_info(data, project_info, message):
    resp = post_analyze(data, "05_story_office", project_info=project_info)
    assert resp.status_code == 422
    assert message in resp.json()["detail"]


def test_analyze_rejects_missing_table(data):
    path = data / "05_story_office"
    files = [("files", ("a.csv", (path / "story_stiffness.csv").read_bytes(), "text/csv"))]
    resp = client.post("/api/analyze", files=files, data={"project_info": (path / "project.json").read_text()})
    assert resp.status_code == 422
    assert "missing table" in resp.json()["detail"]


# ---------- Report ----------


def test_export_report_docx(data):
    result = post_analyze(data, "30_story_highrise").json()
    resp = client.post("/api/export-report", json=result)
    assert resp.status_code == 200
    assert "wordprocessingml" in resp.headers["content-type"]
    assert "San_Francisco_30_Story_High_Rise_ASCE7-22_check.docx" in resp.headers["content-disposition"]

    doc = Document(io.BytesIO(resp.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    cells = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    assert "San Francisco 30-Story High-Rise" in text
    assert "Overall result: FAIL" in text
    assert "Seismic Design Category" in cells
    assert "Output case(s), story drift" in cells and "EQX" in cells
    assert "Engineer of record" in cells
    section = doc.sections[0]
    assert "San Francisco 30-Story High-Rise" in section.header.paragraphs[0].text
    assert "NUMPAGES" in section.footer.paragraphs[0]._p.xml
    assert "ASCE 7-22 Table 12.3-2, Type 1b" in cells
    assert "not permitted in SDC E per 12.3.3.1" in cells
    # every check's formula appears in the detailed section
    for s in result["story_results"]:
        for c in s["checks"]:
            assert c["formula_breakdown"] in cells


def test_export_report_all_pass_and_bad_body(data):
    result = check_building(
        {
            "project_info": {"building_name": "", "risk_category": "II", "drift_is_amplified": True},
            "stories": [
                {
                    "story_name": "S1",
                    "elevation_in": 144.0,
                    "height_in": 144.0,
                    "max_drift_x_in": 0.3,
                    "avg_drift_x_in": 0.3,
                    "max_drift_y_in": 0.3,
                    "avg_drift_y_in": 0.3,
                    "stiffness_x_kip_in": 1000.0,
                    "stiffness_y_kip_in": 1000.0,
                }
            ],
        }
    )
    resp = client.post("/api/export-report", json=result)
    assert resp.status_code == 200
    assert "No irregularities or drift exceedances" in "\n".join(p.text for p in Document(io.BytesIO(resp.content)).paragraphs)
    assert client.post("/api/export-report", json={"nope": 1}).status_code == 422


def test_report_title_block_fields(data):
    result = post_analyze(data, "05_story_office").json()
    result["project_info"].update(project_number="24-117", company="Acme Structural", engineer="J. Doe, SE")
    doc = Document(io.BytesIO(client.post("/api/export-report", json=result).content))
    cells = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    for expected in ("24-117", "Acme Structural", "J. Doe, SE"):
        assert expected in cells
    assert "Project No. 24-117" in doc.sections[0].footer.paragraphs[0].text


# ---------- One-direction input and pasted tables ----------


def test_one_direction_input_marks_other_direction_not_applicable():
    t = simple_tables()
    t[1] = t[1][t[1]["direction"] == "X"]
    b = parse_etabs(t, {"risk_category": "II", "drift_is_amplified": True})
    assert "max_drift_y_in" not in b["stories"][0]
    assert any("Y-direction" in w for w in b["project_info"]["input_warnings"])
    r = check_building(b)
    assert r["basis"]["directions_checked"] == ["X"]
    checks = r["story_results"][0]["checks"]
    y = [c for c in checks if c["check_type"] == "Y-Direction Checks"]
    assert len(y) == 1 and y[0]["status"] == "N/A"
    assert any(c["check_type"] == "Allowable Story Drift (X-Dir)" for c in checks)
    assert r["story_results"][0]["deformations"]["avg_drift_y_in"] == 0.0


def test_no_direction_rows_is_an_error():
    t = simple_tables()
    t[1] = t[1].assign(direction="Z")
    with pytest.raises(ValueError, match="no rows for direction X or Y"):
        parse_etabs(t, {"risk_category": "II"})


def test_pasted_tab_separated_tables():
    text = "Story\tOutput Case\tDirection\tMax Drift\tAvg Drift\nS2\tEQX\tX\t1,000.5\t900\nS1\tEQX\tX\t0.33\t0.30\n"
    df = read_table(text.encode(), "pasted-1.txt")
    assert list(df["max_drift"]) == ["1,000.5", "0.33"]
    assert {"story", "case", "direction"} <= set(df.columns)


def test_frontend_precomputed_samples_match_the_engine():
    # The site shows these on first visit without calling the API; regenerate with
    # `python -m backend.mock_data_gen` whenever the engine changes.
    from pathlib import Path

    from backend.mock_data_gen import sample_result

    for spec in BUILDINGS:
        stored = json.loads((Path("frontend/public/samples") / spec["folder"] / "result.json").read_text())
        assert stored == json.loads(json.dumps(sample_result(Path("data") / spec["folder"])))


# ---------- Round-2 review fixes ----------


def drift_case_tables(rows, n=2, h=100):
    """rows: (story, case, direction, max, avg[, extra]); stories S1..Sn of height h, stiffness uniform."""
    stories = [{"Story": f"S{i}", "Height": h} for i in range(n, 0, -1)]
    drifts = [dict(zip(("Story", "Output Case", "Direction", "Max Drift", "Avg Drift"), r[:5]), **(r[5] if len(r) > 5 else {}))
              for r in rows]
    stiff = [{"Story": f"S{i}", "Output Case": "EQX", "Stiff X": 1000, "Stiff Y": 1000} for i in range(n, 0, -1)]
    return [csv_table(t) for t in tables(stories, drifts, stiff)]


def test_drift_envelope_takes_max_and_avg_separately():
    # Codex N1: A has the larger Max, B the larger Avg; B must govern the center-of-mass drift.
    rows = [(s, c, "X", mx, av) for s in ("S1", "S2") for c, mx, av in (("A", 2.1, 1.8), ("B", 2.05, 2.04))]
    b = parse_etabs(drift_case_tables(rows), {"risk_category": "II"})
    s1 = b["stories"][0]
    assert s1["avg_drift_x_in"] == 2.04 and s1["drift_x_case"] == "B"
    assert s1["max_drift_x_in"] == 2.1 and s1["drift_max_x_case"] == "A"
    res = check_building({**b, "project_info": {**b["project_info"], "cd": 1, "ie": 1}})
    c = next(c for c in res["story_results"][0]["checks"] if c["check_type"] == "Allowable Story Drift (X-Dir)")
    assert c["status"] == "FAIL" and c["demand_value"] == pytest.approx(0.0204) and c["output_case"] == "B"


def test_tir_envelope_over_steps_of_one_case():
    # Codex N2: one case name, two steps; step 2 has TIR 2.0.
    rows = [(s, "EQX", "X", 1.0, 1.0, {"Step Number": 1}) for s in ("S1", "S2")]
    rows.append(("S1", "EQX", "X", 0.5, 0.25, {"Step Number": 2}))
    s1 = parse_etabs(drift_case_tables(rows), {"risk_category": "II"})["stories"][0]
    assert s1["tir_x"] == 2.0 and s1["tir_x_case"] == "EQX step 2"


def test_every_drift_row_is_validated():
    # Codex N6: a non-governing row with Max > 0 and Avg = 0 is still rejected.
    rows = [(s, "EQX", "X", 1.0, 0.9) for s in ("S1", "S2")] + [("S1", "BAD", "X", 0.1, 0.0)]
    with pytest.raises(ValueError, match=r"S1, X, BAD.*Avg Drift is zero"):
        parse_etabs(drift_case_tables(rows), {"risk_category": "II"})


def test_exception_profiles_per_case_from_parser():
    rows = [(f"S{i}", c, "X", v, v) for c, vals in (("A", (1, 1, 1)), ("B", (0.9, 0.1, 0.1))) for i, v in zip((1, 2, 3), vals)]
    b = parse_etabs(drift_case_tables(rows, n=3), {"risk_category": "II"})
    assert b["stories"][0]["exc_drifts_x"] == {"A": 1.0, "B": 0.9}
    assert b["project_info"]["exception_output_cases"] == {"x": ["A", "B"]}


def test_zero_drift_story_warns():
    rows = [("S1", "EQX", "X", 0.0, 0.0), ("S2", "EQX", "X", 1.0, 0.9)]
    info = parse_etabs(drift_case_tables(rows), {"risk_category": "II"})["project_info"]
    assert any("Zero X-direction drift at S1" in w for w in info["input_warnings"])


def test_analyze_rejects_unknown_project_info_field(data):
    info = json.loads((data / "15_story_tower" / "project.json").read_text())
    resp = post_analyze(data, "15_story_tower", project_info=json.dumps({**info, "moment_frame_roh": 1.3}))
    assert resp.status_code == 422 and "moment_frame_roh" in resp.json()["detail"]


def test_analyze_records_input_files(data):
    info = post_analyze(data, "15_story_tower").json()["project_info"]
    files = {f["name"]: f for f in info["input_files"]}
    assert "story_stiffness.csv" in files and len(files["story_stiffness.csv"]["sha256"]) == 64


def test_report_rejects_non_iso_date_and_prints_inputs(data):
    result = post_analyze(data, "15_story_tower").json()
    bad = {**result, "project_info": {**result["project_info"], "report_date": "November 17, 2026"}}
    assert client.post("/api/export-report", json=bad).status_code == 422
    doc = Document(io.BytesIO(client.post("/api/export-report", json=result).content))
    cells = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    assert "story_stiffness.csv" in cells and "SHA-256" in cells
    first_row = doc.tables[1].rows[0]._tr.xml
    assert "tblHeader" in first_row and "cantSplit" in doc.tables[1].rows[1]._tr.xml
