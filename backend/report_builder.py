"""Build the plan-check calculation package (.docx) from a CodeCheckResult dict."""

from __future__ import annotations

import io
from datetime import date

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

STATUS_COLOR = {
    "PASS": RGBColor(0x1E, 0x7B, 0x34),
    "WARNING": RGBColor(0xB3, 0x6B, 0x00),
    "FAIL": RGBColor(0xC0, 0x00, 0x00),
    "N/A": RGBColor(0x5A, 0x6B, 0x7E),
}

TITLE_BLOCK = [
    ("project_number", "Project No."),
    ("company", "Firm"),
    ("engineer", "Prepared by"),
    ("checked_by", "Checked by"),
]

# Parameters as resolved by the checker ("basis"), so defaults are printed too.
BASIS_LABELS = [
    ("risk_category", "Risk Category"),
    ("seismic_design_category", "Seismic Design Category"),
    ("structure_type", "Structure Type (Table 12.12-1)"),
    ("diaphragm", "Diaphragm"),
    ("drift_is_amplified", "Input Drifts Already Amplified"),
    ("cd", "Deflection Amplification Factor, C_d"),
    ("ie", "Importance Factor, I_e"),
    ("rho_applied_to_drift", "Redundancy Factor rho Applied to Drift Limit (12.12.1.1)"),
    ("drift_limit", "Allowable Story Drift Ratio"),
    ("drift_limit_basis", "Drift Limit Basis"),
    ("apply_soft_story_exception", "Section 12.3.2.2 Exceptions Applied"),
    ("torsion_strength_irregular", "Lateral Strength > 75% on One Side of CM (12.3.2.1.1)"),
]

CASE_LABELS = [
    ("drift_output_cases", "Output case(s), story drift (largest drift per story)"),
    ("torsion_output_cases", "Output case(s), torsion (largest TIR per story)"),
    ("stiffness_output_case", "Output case, soft story stiffness (one case per direction)"),
    ("exception_output_case", "Output case, 12.3.2.2 Exception 1 drifts (one case per direction)"),
]

DISCLAIMER = (
    "This package was generated automatically from analysis output. It is a checking aid and does "
    "not replace the judgment of the engineer of record. All inputs, limits and code references "
    "shall be verified against the published ASCE/SEI 7-22 standard before submittal."
)

SCOPE = [
    "Horizontal torsional irregularity, ASCE 7-22 Table 12.3-1 Type 1, using the Torsional Irregularity "
    "Ratio (TIR) of Section 12.3.2.1.1. The input drifts are taken to include accidental torsion with A_x = 1.0.",
    "The strength criterion of Section 12.3.2.1.1 (more than 75% of the lateral strength on one side of the "
    "center of mass) is not computed from the analysis tables; it is taken from the engineer's input when given.",
    "Vertical soft story irregularity, ASCE 7-22 Table 12.3-2, Types 1a and 1b, "
    "including the exceptions of Section 12.3.2.2.",
    "Allowable story drift, ASCE 7-22 Section 12.12.1 and Table 12.12-1, with drift amplified per Section 12.8.6. "
    "Edge drift is used where the story is torsionally irregular in SDC C to F.",
    "Story drift at the center of mass is approximated by the average of the drifts at the two ends of the story. "
    "This may be unconservative for plans whose center of mass is far from the geometric center.",
    "PASS = regular or within limit. WARNING = irregularity exists and is permitted; the follow-up requirements "
    "are listed under Code-Triggered Action Items. FAIL = prohibited by Section 12.3.3.1 or drift exceeds the "
    "allowable. N/A = not applicable or not computable from the data; the reason is stated.",
    "Not covered: other irregularity types (including weak story), P-delta stability, diaphragm deformation, "
    "and the numerical value of A_x.",
]


def _status_run(paragraph, status: str):
    run = paragraph.add_run(status)
    run.bold = True
    run.font.color.rgb = STATUS_COLOR.get(status, RGBColor(0, 0, 0))
    return run


def _table(doc, headers, widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    for cell, text in zip(table.rows[0].cells, headers):
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.bold = True
    return table


def _row(table, values, status_col=None):
    cells = table.add_row().cells
    for i, value in enumerate(values):
        cells[i].text = ""
        if i == status_col:
            _status_run(cells[i].paragraphs[0], value)
        else:
            cells[i].paragraphs[0].add_run(str(value))
    return cells


def _field(paragraph, instruction: str):
    """Insert a Word field such as PAGE or NUMPAGES; Word fills in the value when it opens the file."""
    run = paragraph.add_run()
    for tag, attrs, text in (
        ("w:fldChar", {"w:fldCharType": "begin"}, None),
        ("w:instrText", {"xml:space": "preserve"}, instruction),
        ("w:fldChar", {"w:fldCharType": "end"}, None),
    ):
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        if text:
            el.text = text
        run._r.append(el)


def _header_footer(section, building: str, project_number: str | None):
    header = section.header.paragraphs[0]
    header.text = f"{building}\tASCE/SEI 7-22 Seismic Irregularity and Story Drift Check"
    footer = section.footer.paragraphs[0]
    footer.text = (f"Project No. {project_number}" if project_number else "") + "\tPage "
    _field(footer, "PAGE")
    footer.add_run(" of ")
    _field(footer, "NUMPAGES")
    for p in (header, footer):
        for run in p.runs:
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(0x5A, 0x6B, 0x7E)


STRUCTURE_TYPES = {
    "other": "All other structures",
    "four_story_or_less_drift_tolerant": "Four stories or fewer, drift-tolerant finishes",
    "masonry_cantilever_shear_wall": "Masonry cantilever shear wall",
    "other_masonry_shear_wall": "Other masonry shear wall",
}


def _show(value) -> str:
    if value in STRUCTURE_TYPES:
        return STRUCTURE_TYPES[value]
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).replace("_", " ") if isinstance(value, str) else str(value)


def _signature_block(doc, info: dict):
    doc.add_heading("Review and Approval", level=2)
    t = _table(doc, ["Role", "Name", "Signature", "Date"])
    for role, key in (("Prepared by", "engineer"), ("Checked by", "checked_by"), ("Engineer of record", None)):
        cells = _row(t, [role, info.get(key) or "" if key else "", "", ""])
        cells[2].paragraphs[0].add_run("\n")  # room to sign
    doc.add_paragraph("Engineer's seal:")
    box = doc.add_table(rows=1, cols=1)
    box.style = "Table Grid"
    box.autofit = False
    box.columns[0].width = Inches(2.2)
    cell = box.rows[0].cells[0]
    cell.width = Inches(2.2)
    cell.paragraphs[0].add_run("\n\n\n\n\n")


def _fmt(x) -> str:
    if x is None:
        return "-"
    return f"{x:,.4g}" if isinstance(x, (int, float)) else str(x)


def _dc(x) -> str:
    return "-" if x is None else f"{x:.2f}"


def _report_date(info: dict) -> str:
    """The user's local date when the client sends it (the server runs on UTC)."""
    raw = info.get("report_date")
    if raw:
        try:
            return date.fromisoformat(str(raw)).strftime("%B %d, %Y")
        except ValueError:
            pass
    return date.today().strftime("%B %d, %Y")


def _cases(value) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{d.upper()}: {_cases(v)}" for d, v in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(map(str, value))
    return str(value)


def build_report(result: dict, project_info: dict | None = None) -> bytes:
    """Return the .docx file content for a CodeCheckResult."""
    summary = result["summary"]
    stories = result["story_results"]
    project_info = project_info or result.get("project_info") or {}

    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Inches(0.8))
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10)
    building = summary.get("building_name") or "Untitled Project"
    _header_footer(section, building, project_info.get("project_number"))

    # ---- Cover ----
    title = doc.add_heading("Seismic Irregularity and Story Drift Check", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("ASCE/SEI 7-22 Chapter 12 - Structural Calculation Package")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(building)
    run.bold = True
    run.font.size = Pt(14)

    t = _table(doc, ["Project", building])
    for key, label in TITLE_BLOCK:
        if project_info.get(key):
            _row(t, [label, project_info[key]])
    _row(t, ["Date", _report_date(project_info)])
    _row(t, ["Governing standard", "ASCE/SEI 7-22, Chapter 12"])

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Overall result: ")
    _status_run(p, summary["overall_status"]).font.size = Pt(16)

    doc.add_heading("Results and Design Parameters", level=2)
    t = _table(doc, ["Item", "Value"])
    _row(t, ["Stories checked", summary["total_stories"]])
    _row(t, ["Checks failing (FAIL)", summary["total_violations"]])
    if "total_warnings" in summary:
        _row(t, ["Irregularities flagged (WARNING)", summary["total_warnings"]])
    if summary.get("total_not_applicable"):
        _row(t, ["Checks not applicable or not computable (N/A)", summary["total_not_applicable"]])
    _row(t, ["Maximum story drift D/C ratio", _fmt(summary["max_dc_ratio"])])
    basis = result.get("basis") or {}
    for key, label in BASIS_LABELS:
        value = basis.get(key, project_info.get(key))
        if key == "torsion_strength_irregular" and value is None and basis:
            value = "Not evaluated"
        if value is not None:
            _row(t, [label, _show(value)])
    for key, label in CASE_LABELS:
        if project_info.get(key):
            _row(t, [label, _cases(project_info[key])])
    units = project_info.get("units") or {}
    _row(t, ["Units", f"{units.get('length', 'in')}, {units.get('force', 'kips')}"])

    warnings = project_info.get("input_warnings") or []
    if warnings:
        doc.add_heading("Input Data Warnings", level=2)
        for w in warnings:
            doc.add_paragraph(w, style="List Bullet")

    doc.add_heading("Scope and Basis", level=2)
    for line in SCOPE:
        doc.add_paragraph(line, style="List Bullet")
    doc.add_paragraph(DISCLAIMER).runs[0].italic = True
    _signature_block(doc, project_info)

    # ---- Flagged items ----
    doc.add_page_break()
    doc.add_heading("1. Summary of Flagged Items", level=1)
    flagged = [(s, c) for s in stories for c in s["checks"] if c["status"] in ("FAIL", "WARNING")]
    flagged.sort(key=lambda sc: sc[1]["status"] != "FAIL")  # FAIL first, story order kept
    if not flagged:
        doc.add_paragraph("No irregularities or drift exceedances were found.")
    else:
        t = _table(doc, ["Story", "Check", "Code Reference", "Output Case", "Demand", "Limit", "Ratio", "Status"])
        for s, c in flagged:
            cells = _row(
                t,
                [
                    s["story_name"],
                    c["check_type"],
                    c["code_reference"],
                    c.get("output_case") or "-",
                    _fmt(c["demand_value"]),
                    _fmt(c["capacity_limit"]),
                    _dc(c["dc_ratio"]),
                    c["status"],
                ],
                status_col=7,
            )
            if c["status"] == "FAIL":
                for cell in cells[:7]:
                    for run in cell.paragraphs[0].runs:
                        run.font.color.rgb = STATUS_COLOR["FAIL"]
        doc.add_paragraph(
            "Ratio is demand / limit. For drift it is a demand / capacity ratio; for irregularities it only "
            "measures distance from the code threshold, and a value above 1.0 is not by itself a violation."
        ).runs[0].italic = True

    actions = summary.get("action_items") or []
    doc.add_heading("Code-Triggered Action Items", level=2)
    if actions:
        doc.add_paragraph("Each item must be addressed in the design and initialed by the engineer of record.")
        t = _table(doc, ["Required action", "Triggered at", "Done (initials)"])
        for item in actions:
            _row(t, [item["action"], ", ".join(item["stories"]), ""])
    else:
        doc.add_paragraph("No follow-up requirements were triggered by the checks in this package.")

    skipped = [(s, c) for s in stories for c in s["checks"] if c["status"] == "N/A"]
    if skipped:
        doc.add_heading("Checks Not Applicable or Not Computable", level=2)
        t = _table(doc, ["Story", "Check", "Reason"])
        for s, c in skipped:
            _row(t, [s["story_name"], c["check_type"], c["formula_breakdown"]])

    # ---- Story status overview ----
    doc.add_heading("2. Story Status Overview", level=1)
    t = _table(doc, ["Story", "Elevation (in)", "Height (in)", "Max Ratio", "Status"])
    for s in reversed(stories):  # top-down, as on an elevation
        _row(
            t,
            [s["story_name"], _fmt(s["elevation_in"]), _fmt(s["height_in"]), f"{s['max_dc_ratio']:.2f}", s["status"]],
            status_col=4,
        )

    # ---- Detailed calculations ----
    doc.add_page_break()
    doc.add_heading("3. Detailed Calculations by Story", level=1)
    for s in reversed(stories):
        h = doc.add_heading(level=2)
        h.add_run(f"{s['story_name']}  (elev. {_fmt(s['elevation_in'])} in, h_sx = {_fmt(s['height_in'])} in)  ")
        _status_run(h, s["status"])
        t = _table(doc, ["Check", "Code Reference", "Output Case", "Calculation", "Ratio", "Status"])
        for c in s["checks"]:
            text = c["formula_breakdown"]
            if c.get("actions"):
                text += "\nRequired: " + "; ".join(c["actions"])
            _row(
                t,
                [c["check_type"], c["code_reference"], c.get("output_case") or "-", text, _dc(c["dc_ratio"]), c["status"]],
                status_col=5,
            )

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
