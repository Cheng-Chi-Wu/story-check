"""FastAPI app.   uvicorn backend.main:app --reload

POST /api/analyze        multipart: files[] (the three ETABS tables) + project_info (JSON string)
                         -> CodeCheckResult, plus the project_info that was used
POST /api/export-report  JSON body: the /api/analyze response -> .docx download
GET  /api/health
"""

from __future__ import annotations

import json
import os
import re

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.code_checker import check_building
from backend.parser import parse_etabs, read_tables
from backend.report_builder import build_report

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_FILES = 6
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

app = FastAPI(title="Structural Code-Check Copilot", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # Comma-separated origins, e.g. "https://app.example.com"; defaults to the local Next.js dev server.
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    # Optional regex, e.g. "https://.*\\.vercel\\.app" to also allow Vercel preview deployments.
    allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX") or None,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    files: list[UploadFile] = File(..., description="Story definitions, drifts and stiffness tables (CSV/XLSX)"),
    project_info: str = Form(..., description="JSON object, see blueprint section 5.1"),
    length_unit: str = Form("in"),
    force_unit: str = Form("kip"),
    case_x: str | None = Form(None),
    case_y: str | None = Form(None),
):
    try:
        info = json.loads(project_info)
        if not isinstance(info, dict):
            raise ValueError("project_info must be a JSON object")

        if len(files) > MAX_FILES:
            raise ValueError(f"at most {MAX_FILES} files can be uploaded at once")
        tables = []
        for f in files:
            content = await f.read()
            if len(content) > MAX_UPLOAD_BYTES:
                raise ValueError(f"{f.filename}: file is larger than 20 MB")
            tables.extend(read_tables(content, f.filename))

        building = parse_etabs(tables, info, length_unit, force_unit, case_x or None, case_y or None)
        result = check_building(building)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"project_info is not valid JSON: {e}") from None
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e)) from None

    result["project_info"] = building["project_info"]
    return result


@app.post("/api/export-report")
def export_report(result: dict):
    try:
        content = build_report(result)
    except (KeyError, TypeError) as e:
        raise HTTPException(422, f"body is not a valid CodeCheckResult: {e}") from None

    name = re.sub(r"[^A-Za-z0-9]+", "_", result["summary"].get("building_name") or "building").strip("_")
    return Response(
        content,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{name or "building"}_ASCE7-22_check.docx"'},
    )
