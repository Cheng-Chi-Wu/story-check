"use client";

import { useEffect, useRef } from "react";
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
      <Stat value={s.max_dc_ratio.toFixed(2)} label="Max D/C" />
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
              {c.code_reference} — D/C {c.dc_ratio.toFixed(2)}
            </div>
            <p className="mt-1.5 font-mono text-xs leading-relaxed break-words">{c.formula_breakdown}</p>
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
  const stories = [...result.story_results].reverse();
  const scale = Math.max(1, ...stories.map((s) => s.max_dc_ratio));
  const open = useRef<HTMLLIElement>(null);

  useEffect(() => {
    // Scroll only the list itself; scrollIntoView would also shift the page behind it.
    const row = open.current;
    const scroller = row?.closest<HTMLElement>("[data-story-scroll]");
    if (!row || !scroller) return;
    scroller.scrollTop += row.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
  }, [selected]);

  return (
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
  );
}
