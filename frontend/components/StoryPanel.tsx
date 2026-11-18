"use client";

import { useEffect, useRef, useState } from "react";
import { STATUS_COLOR, STATUS_LABEL, type CodeCheckResult, type Status, type StoryResult } from "@/lib/types";

export function StatusTag({ status, large }: { status: Status; large?: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold ${large ? "text-base" : "text-xs"}`}
      style={{ color: STATUS_COLOR[status] }}
    >
      <span aria-hidden className="inline-block size-2.5" style={{ background: STATUS_COLOR[status] }} />
      {STATUS_LABEL[status]}
    </span>
  );
}

function Stat({ value, label, tone }: { value: string | number; label: string; tone?: Status }) {
  return (
    <div className="px-3 py-2">
      <div
        className="font-display text-2xl font-semibold tabular-nums"
        style={tone ? { color: STATUS_COLOR[tone] } : undefined}
      >
        {value}
      </div>
      <div className="text-xs text-steel">{label}</div>
    </div>
  );
}

export function Summary({ result }: { result: CodeCheckResult }) {
  const s = result.summary;
  return (
    <div className="grid grid-cols-4 divide-x divide-line border-b border-line bg-sheet">
      <Stat value={s.total_stories} label="Stories" />
      <Stat value={s.total_violations} label="Failed checks" tone={s.total_violations ? "FAIL" : undefined} />
      <Stat value={s.total_warnings ?? 0} label="Irregularities" tone={s.total_warnings ? "WARNING" : undefined} />
      <Stat
        value={s.max_dc_ratio.toFixed(2)}
        label="Max drift D/C"
        tone={s.max_dc_ratio > 1 ? "FAIL" : undefined}
      />
    </div>
  );
}

/** Input warnings and the follow-up requirements the checks triggered. */
export function Notices({ result }: { result: CodeCheckResult }) {
  const warnings = (result.project_info?.input_warnings as string[] | undefined) ?? [];
  const actions = result.summary.action_items ?? [];
  if (!warnings.length && !actions.length) return null;
  return (
    <div className="flex flex-col gap-2 border-b border-line bg-sheet p-3">
      {warnings.length > 0 && (
        <div className="border-l-2 border-warn bg-warn/10 px-2.5 py-2 text-xs">
          <p className="font-semibold">Check the input data</p>
          <ul className="mt-1 list-disc pl-4">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {actions.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold">Required follow-up ({actions.length})</summary>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {actions.map((a) => (
              <li key={a.action} className="border-l-2 border-line pl-2">
                {a.action}
                <span className="block text-steel">{a.stories.join(", ")}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Detail({ story }: { story: StoryResult }) {
  return (
    <div className="border-t border-line bg-paper/60 px-3 py-3">
      <ul className="flex flex-col gap-3">
        {story.checks.map((c) => (
          <li key={c.check_type} className="border-l-2 pl-2.5" style={{ borderColor: STATUS_COLOR[c.status] }}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-medium">{c.check_type}</span>
              <StatusTag status={c.status} />
            </div>
            <div className="mt-0.5 text-xs text-steel">
              {c.code_reference}
              {c.dc_ratio !== null && ` — ratio ${c.dc_ratio.toFixed(2)}`}
              {c.output_case && ` — case ${c.output_case}`}
            </div>
            <p className="mt-1.5 font-mono text-xs leading-relaxed break-words">{c.formula_breakdown}</p>
            {c.actions && c.actions.length > 0 && (
              <ul className="mt-1.5 list-disc pl-4 text-xs">
                {c.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface Props {
  result: CodeCheckResult;
  selected: string | null;
  onSelect: (name: string | null) => void;
}

/** Stories listed top-down like an elevation; the selected one opens its calculations. */
export default function StoryPanel({ result, selected, onSelect }: Props) {
  const all = [...result.story_results].reverse();
  const flagged = all.filter((s) => s.status === "FAIL" || s.status === "WARNING");
  const [issuesOnly, setIssuesOnly] = useState(false);
  const stories = issuesOnly ? flagged : all;
  const scale = Math.max(1, ...all.map((s) => s.max_dc_ratio));
  const open = useRef<HTMLLIElement>(null);

  useEffect(() => {
    // Scroll only the list itself; scrollIntoView would also shift the page behind it.
    const row = open.current;
    const scroller = row?.closest<HTMLElement>("[data-story-scroll]");
    if (!row || !scroller) return;
    const bar = scroller.querySelector<HTMLElement>("[data-story-filter]")?.offsetHeight ?? 0;
    scroller.scrollTop += row.getBoundingClientRect().top - scroller.getBoundingClientRect().top - bar;
  }, [selected]);

  return (
    <>
    <div data-story-filter className="sticky top-0 z-10 flex items-center gap-1 border-b border-line bg-sheet px-3 py-1.5 text-xs">
      {[
        [false, `All stories (${all.length})`],
        [true, `Issues only (${flagged.length})`],
      ].map(([value, label]) => (
        <button
          key={String(value)}
          type="button"
          aria-pressed={issuesOnly === value}
          onClick={() => setIssuesOnly(value as boolean)}
          className={`px-2 py-1 ${issuesOnly === value ? "bg-ink text-white" : "text-steel hover:text-ink"}`}
        >
          {label as string}
        </button>
      ))}
    </div>
    {stories.length === 0 && <p className="px-3 py-4 text-sm text-steel">No failed or irregular stories.</p>}
    <ol className="divide-y divide-line">
      {stories.map((s) => {
        const isOpen = s.story_name === selected;
        return (
          <li key={s.story_name} ref={isOpen ? open : undefined}>
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => onSelect(isOpen ? null : s.story_name)}
              className={`grid w-full grid-cols-[5.5rem_1fr_5rem] items-center gap-3 px-3 py-2 text-left hover:bg-paper ${
                isOpen ? "bg-paper" : "bg-sheet"
              }`}
            >
              <span>
                <span className="block text-sm font-medium">{s.story_name}</span>
                <span className="block text-xs tabular-nums text-steel">
                  {(s.elevation_in / 12).toFixed(1)} ft
                </span>
              </span>
              <span className="flex items-center gap-2">
                <span className="relative h-2 flex-1 bg-paper" aria-hidden>
                  <span
                    className="absolute inset-y-0 left-0"
                    style={{ width: `${(s.max_dc_ratio / scale) * 100}%`, background: STATUS_COLOR[s.status] }}
                  />
                  {/* D/C = 1.0 marker */}
                  <span className="absolute inset-y-[-3px] w-px bg-ink" style={{ left: `${(1 / scale) * 100}%` }} />
                </span>
                <span className="w-9 text-right text-xs tabular-nums">{s.max_dc_ratio.toFixed(2)}</span>
              </span>
              <span className="justify-self-end">
                <StatusTag status={s.status} />
              </span>
            </button>
            {isOpen && <Detail story={s} />}
          </li>
        );
      })}
    </ol>
    </>
  );
}
