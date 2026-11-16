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
    with pytest.raises(ValueError, match="missing drift or stiffness data: S1"):
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
    assert ("Story20", "Torsional Irregularity (Y-Dir)", "FAIL") in f
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
    assert "Output case(s) used, X direction" in cells and "EQX" in cells
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
    assert "All checks pass" in "\n".join(p.text for p in Document(io.BytesIO(resp.content)).paragraphs)
    assert client.post("/api/export-report", json={"nope": 1}).status_code == 422


def test_report_title_block_fields(data):
    result = post_analyze(data, "05_story_office").json()
    result["project_info"].update(project_number="24-117", company="Acme Structural", engineer="J. Doe, SE")
    doc = Document(io.BytesIO(client.post("/api/export-report", json=result).content))
    cells = "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    for expected in ("24-117", "Acme Structural", "J. Doe, SE"):
        assert expected in cells
    assert "Project No. 24-117" in doc.sections[0].footer.paragraphs[0].text
