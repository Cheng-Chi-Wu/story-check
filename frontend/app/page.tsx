"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import SetupPanel from "@/components/SetupPanel";
import StoryPanel, { StatusTag, Summary } from "@/components/StoryPanel";
import { analyze, exportReport, loadSample } from "@/lib/api";
import type { CodeCheckResult, ProjectForm } from "@/lib/types";

const BuildingViewer = dynamic(() => import("@/components/BuildingViewer"), {
  ssr: false,
  loading: () => <p className="p-6 text-sm text-steel">Loading the model…</p>,
});

const DEFAULTS: ProjectForm = {
  building_name: "",
  risk_category: "II",
  seismic_design_category: "D",
  structure_type: "other",
  diaphragm: "rigid",
  cd: "5.5",
  ie: "",
  drift_is_amplified: false,
  moment_frame_rho: "",
  length_unit: "in",
  force_unit: "kip",
  project_number: "",
  company: "",
  engineer: "",
  checked_by: "",
};

/** First story worth looking at: a failing one, else an irregular one. */
function firstFlagged(result: CodeCheckResult): string | null {
  const stories = result.story_results;
  return (stories.find((s) => s.status === "FAIL") ?? stories.find((s) => s.status === "WARNING"))?.story_name ?? null;
}

export default function Home() {
  const [form, setForm] = useState<ProjectForm>(DEFAULTS);
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<CodeCheckResult | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(runFiles: File[], runForm: ProjectForm) {
    setBusy(true);
    setError(null);
    try {
      const r = await analyze(runFiles, runForm);
      setResult(r);
      setSelected(firstFlagged(r));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function sample(folder: string) {
    setBusy(true);
    setError(null);
    try {
      const { files: f, info } = await loadSample(folder);
      const next: ProjectForm = {
        ...DEFAULTS,
        ...Object.fromEntries(Object.entries(info).map(([k, v]) => [k, typeof v === "number" ? String(v) : v])),
      };
      setFiles(f);
      setForm(next);
      await run(f, next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  async function download() {
    if (!result) return;
    setExporting(true);
    setError(null);
    try {
      await exportReport(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col lg:h-screen">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line bg-sheet px-4 py-3">
        <div>
          <h1 className="font-display text-xl font-semibold leading-tight">Story Check</h1>
          <p className="text-xs text-steel">ASCE 7-22 Chapter 12: torsion, soft story and drift</p>
        </div>
        {result && (
          <div className="flex items-center gap-3 border-l border-line pl-6">
            <span className="text-sm font-medium">{result.summary.building_name || "Untitled building"}</span>
            <StatusTag status={result.summary.overall_status} large />
          </div>
        )}
        <button
          type="button"
          onClick={download}
          disabled={!result || exporting}
          className="ml-auto border border-ink px-3 py-2 text-sm font-semibold disabled:border-line disabled:text-steel"
        >
          {exporting ? "Building report…" : "Download calculation report (.docx)"}
        </button>
      </header>

      {error && (
        <div role="alert" className="flex items-start gap-3 border-b border-fail/40 bg-fail/10 px-4 py-2 text-sm text-fail">
          <span className="flex-1">{error}</span>
          <button type="button" className="underline" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="grid flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[19rem_minmax(0,1fr)_26rem]">
        <aside className="border-b border-line lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <SetupPanel
            form={form}
            onForm={(patch) => setForm((f) => ({ ...f, ...patch }))}
            files={files}
            onFiles={setFiles}
            onRun={() => run(files, form)}
            onSample={sample}
            busy={busy}
          />
        </aside>

        <main className="relative min-h-[420px] lg:min-h-0">
          {result ? (
            <BuildingViewer stories={result.story_results} selected={selected} onSelect={setSelected} />
          ) : (
            <div className="flex h-full items-center justify-center p-8">
              <div className="max-w-md">
                <h2 className="font-display text-3xl font-semibold leading-tight">
                  See which stories fail before the plan checker does.
                </h2>
                <p className="mt-3 text-steel">
                  Add your three ETABS tables on the left and run the check. Each story is tested for torsional
                  irregularity, soft story and allowable drift, with the calculation shown for every result.
                </p>
              </div>
            </div>
          )}
        </main>

        <aside className="border-t border-line bg-sheet lg:flex lg:min-h-0 lg:flex-col lg:border-l lg:border-t-0">
          {result ? (
            <>
              <Summary result={result} />
              <div data-story-scroll className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
                <StoryPanel result={result} selected={selected} onSelect={setSelected} />
              </div>
              <p className="border-t border-line px-3 py-2 text-xs text-steel">
                A checking aid. The engineer of record verifies every limit against ASCE/SEI 7-22.
              </p>
            </>
          ) : (
            <p className="p-4 text-sm text-steel">Story-by-story results appear here after a check.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
