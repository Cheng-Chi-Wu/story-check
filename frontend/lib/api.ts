import type { CodeCheckResult, ProjectForm } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fail(resp: Response): Promise<never> {
  let message = `The server returned ${resp.status}.`;
  try {
    const body = await resp.json();
    if (typeof body.detail === "string") message = body.detail;
  } catch {
    /* keep the generic message */
  }
  throw new Error(message);
}

async function send(path: string, init: RequestInit): Promise<Response> {
  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, init);
  } catch {
    throw new Error(`Can't reach the analysis server at ${API}. Start it, then run the check again.`);
  }
  if (!resp.ok) await fail(resp);
  return resp;
}

export function toProjectInfo(form: ProjectForm): Record<string, unknown> {
  const num = (s: string) => (s.trim() === "" ? undefined : Number(s));
  const info: Record<string, unknown> = {
    building_name: form.building_name.trim(),
    risk_category: form.risk_category,
    seismic_design_category: form.seismic_design_category,
    structure_type: form.structure_type,
    diaphragm: form.diaphragm,
    drift_is_amplified: form.drift_is_amplified,
    cd: num(form.cd),
    ie: num(form.ie),
    moment_frame_rho: num(form.moment_frame_rho),
  };
  // Title-block details for the report; left out when blank.
  for (const k of ["project_number", "company", "engineer", "checked_by"] as const) {
    if (form[k].trim()) info[k] = form[k].trim();
  }
  for (const k of Object.keys(info)) if (info[k] === undefined) delete info[k];
  return info;
}

export async function analyze(files: File[], form: ProjectForm): Promise<CodeCheckResult> {
  const body = new FormData();
  for (const f of files) body.append("files", f, f.name);
  body.append("project_info", JSON.stringify(toProjectInfo(form)));
  body.append("length_unit", form.length_unit);
  body.append("force_unit", form.force_unit);
  const resp = await send("/api/analyze", { method: "POST", body });
  return resp.json();
}

export async function exportReport(result: CodeCheckResult): Promise<void> {
  const resp = await send("/api/export-report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(result),
  });
  const name = /filename="([^"]+)"/.exec(resp.headers.get("Content-Disposition") ?? "")?.[1] ?? "story_check.docx";
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const SAMPLES = [
  { folder: "05_story_office", label: "5-story office" },
  { folder: "15_story_tower", label: "15-story tower" },
  { folder: "30_story_highrise", label: "30-story high-rise" },
];

const SAMPLE_TABLES = ["story_definitions", "story_max_over_avg_drifts", "story_stiffness"];

export async function loadSample(folder: string): Promise<{ files: File[]; info: Record<string, unknown> }> {
  const base = `/samples/${folder}`;
  const files = await Promise.all(
    SAMPLE_TABLES.map(async (t) => {
      const resp = await fetch(`${base}/${t}.csv`);
      if (!resp.ok) throw new Error(`Sample file ${t}.csv is missing.`);
      return new File([await resp.blob()], `${t}.csv`, { type: "text/csv" });
    }),
  );
  const info = await (await fetch(`${base}/project.json`)).json();
  return { files, info };
}
