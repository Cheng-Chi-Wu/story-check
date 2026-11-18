"use client";

import { useRef, useState } from "react";
import { SAMPLES } from "@/lib/api";
import type { ProjectForm } from "@/lib/types";

interface Props {
  form: ProjectForm;
  onForm: (patch: Partial<ProjectForm>) => void;
  files: File[];
  onFiles: (files: File[]) => void;
  onRun: () => void;
  onSample: (folder: string) => void;
  busy: boolean;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-steel">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-steel">{hint}</span>}
    </label>
  );
}

export default function SetupPanel({ form, onForm, files, onFiles, onRun, onSample, busy }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [pasted, setPasted] = useState("");

  const add = (list: FileList | null) => {
    if (!list?.length) return;
    const byName = new Map(files.map((f) => [f.name, f]));
    for (const f of Array.from(list)) byName.set(f.name, f);
    onFiles([...byName.values()]);
  };

  return (
    <div className="flex flex-col gap-5 p-4">
      <section>
        <h2 className="font-display text-lg font-semibold">ETABS tables</h2>
        <p className="mt-1 text-sm text-steel">
          Export Story Definitions, Story Max Over Avg Drifts and Story Stiffness as CSV or Excel.
        </p>
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            add(e.dataTransfer.files);
          }}
          className={`mt-3 w-full border border-dashed px-3 py-5 text-sm ${
            over ? "border-accent bg-accent/5" : "border-steel/60 bg-sheet"
          }`}
        >
          Drop the three files here, or choose files
        </button>
        <p className="mt-2 text-xs text-steel">
          Files are processed in memory to run the check and are not saved on our servers.
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept=".csv,.txt,.tsv,.xlsx,.xls"
          className="sr-only"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
        {files.length > 0 && (
          <ul className="mt-2 divide-y divide-line border border-line bg-sheet text-sm">
            {files.map((f) => (
              <li key={f.name} className="flex items-center justify-between gap-2 px-2 py-1.5">
                <span className="truncate">{f.name}</span>
                <button
                  type="button"
                  className="shrink-0 text-xs text-steel underline"
                  onClick={() => onFiles(files.filter((x) => x !== f))}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-xs font-medium text-steel">Or paste a table copied from ETABS</summary>
          <textarea
            className="field mt-2 h-24 font-mono text-xs"
            placeholder="Select the table in ETABS, including the header row, press Ctrl+C and paste here"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
          />
          <button
            type="button"
            disabled={!pasted.trim()}
            onClick={() => {
              const n = files.filter((f) => f.name.startsWith("pasted-table-")).length + 1;
              onFiles([...files, new File([pasted], `pasted-table-${n}.txt`, { type: "text/plain" })]);
              setPasted("");
            }}
            className="mt-1.5 border border-line bg-sheet px-2 py-1 text-xs hover:border-accent disabled:opacity-50"
          >
            Add pasted table
          </button>
        </details>
        <p className="mt-3 text-xs text-steel">No files handy? Load a sample building:</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {SAMPLES.map((s) => (
            <button
              key={s.folder}
              type="button"
              disabled={busy}
              onClick={() => onSample(s.folder)}
              className="border border-line bg-sheet px-2 py-1 text-xs hover:border-accent disabled:opacity-50"
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-semibold">Project</h2>
        <Field label="Building name">
          <input className="field" value={form.building_name} onChange={(e) => onForm({ building_name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Risk category">
            <select
              className="field"
              value={form.risk_category}
              onChange={(e) => onForm({ risk_category: e.target.value as ProjectForm["risk_category"] })}
            >
              {["I", "II", "III", "IV"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
          <Field label="Seismic design category">
            <select
              className="field"
              value={form.seismic_design_category}
              onChange={(e) =>
                onForm({ seismic_design_category: e.target.value as ProjectForm["seismic_design_category"] })
              }
            >
              {["B", "C", "D", "E", "F"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Structure type (Table 12.12-1)">
          <select className="field" value={form.structure_type} onChange={(e) => onForm({ structure_type: e.target.value })}>
            <option value="other">All other structures</option>
            <option value="four_story_or_less_drift_tolerant">4 stories or fewer, drift-tolerant finishes</option>
            <option value="masonry_cantilever_shear_wall">Masonry cantilever shear wall</option>
            <option value="other_masonry_shear_wall">Other masonry shear wall</option>
          </select>
        </Field>
        <Field label="Diaphragm">
          <select
            className="field"
            value={form.diaphragm}
            onChange={(e) => onForm({ diaphragm: e.target.value as ProjectForm["diaphragm"] })}
          >
            <option value="rigid">Rigid</option>
            <option value="semirigid">Semirigid</option>
            <option value="flexible">Flexible (no torsion check)</option>
          </select>
        </Field>
        <Field
          label="Lateral strength > 75% on one side of CM"
          hint="Section 12.3.2.1.1 strength criterion. Not in the ETABS tables, so state it here."
        >
          <select
            className="field"
            value={form.torsion_strength}
            onChange={(e) => onForm({ torsion_strength: e.target.value as ProjectForm["torsion_strength"] })}
          >
            <option value="unknown">Not evaluated</option>
            <option value="no">No</option>
            <option value="yes">Yes (torsionally irregular)</option>
          </select>
        </Field>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-semibold">Drift amplification</h2>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={form.drift_is_amplified}
            onChange={(e) => onForm({ drift_is_amplified: e.target.checked })}
          />
          <span>Exported drifts already include C<sub>d</sub> / I<sub>e</sub></span>
        </label>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Cd">
            <input
              className="field"
              inputMode="decimal"
              disabled={form.drift_is_amplified}
              value={form.cd}
              onChange={(e) => onForm({ cd: e.target.value })}
            />
          </Field>
          <Field label="Ie">
            <input
              className="field"
              inputMode="decimal"
              placeholder="By risk cat."
              disabled={form.drift_is_amplified}
              value={form.ie}
              onChange={(e) => onForm({ ie: e.target.value })}
            />
          </Field>
        </div>
        <Field
          label="Redundancy factor ρ (moment frames only)"
          hint="For systems of moment frames only, in SDC D to F (12.12.1.1). Not for dual systems."
        >
          <select
            className="field"
            value={form.moment_frame_rho}
            onChange={(e) => onForm({ moment_frame_rho: e.target.value })}
          >
            <option value="">Not a moment-frame-only system</option>
            <option value="1.0">1.0</option>
            <option value="1.3">1.3</option>
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Length unit in files">
            <select className="field" value={form.length_unit} onChange={(e) => onForm({ length_unit: e.target.value })}>
              {["in", "ft", "mm", "cm", "m"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
          <Field label="Force unit in files">
            <select className="field" value={form.force_unit} onChange={(e) => onForm({ force_unit: e.target.value })}>
              {["kip", "lb", "kN", "N"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-semibold">Report title block</h2>
        <p className="-mt-2 text-sm text-steel">Optional. Printed on the calculation report.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Project no.">
            <input className="field" value={form.project_number} onChange={(e) => onForm({ project_number: e.target.value })} />
          </Field>
          <Field label="Firm">
            <input className="field" value={form.company} onChange={(e) => onForm({ company: e.target.value })} />
          </Field>
          <Field label="Prepared by">
            <input className="field" value={form.engineer} onChange={(e) => onForm({ engineer: e.target.value })} />
          </Field>
          <Field label="Checked by">
            <input className="field" value={form.checked_by} onChange={(e) => onForm({ checked_by: e.target.value })} />
          </Field>
        </div>
      </section>

      <button
        type="button"
        onClick={onRun}
        disabled={busy || files.length === 0}
        className="bg-ink px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
      >
        {busy ? "Checking…" : "Run check"}
      </button>
    </div>
  );
}
