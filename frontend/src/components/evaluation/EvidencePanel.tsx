import { cn, formatNumber } from "../../lib/utils.ts";
import type { EvidenceEntry, Report } from "../../types/evaluation.ts";

function Column({ label, entries }: { label: "A" | "B"; entries: EvidenceEntry[] }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-800">Response {label}</h3>
      <ul className="space-y-3">
        {entries.map((e, index) => (
          <li key={`${e.criterion_id}-${index}`} className="rounded-md border border-slate-200 p-3">
            <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-slate-700">{e.criterion_name}</span>
              <span className={cn("tabular-nums", e.passed ? "text-emerald-700" : "text-red-700")}>
                {formatNumber(e.score)}/{e.scale_max} · {e.passed ? "pass" : "fail"}
              </span>
            </div>
            <blockquote
              className={cn(
                "border-l-4 pl-3 text-sm italic text-slate-800",
                e.passed ? "border-emerald-300" : "border-red-300",
              )}
            >
              “{e.quote}”
            </blockquote>
            <p className="mt-1.5 text-xs text-slate-600">
              {e.supports}
              {e.location && <span className="ml-1 font-mono text-slate-400">({e.location})</span>}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Verbatim quotes backing each criterion score, grouped by response. */
export function EvidencePanel({ report }: { report: Report }) {
  return (
    <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className="mb-3 text-base font-semibold text-slate-900">
        Evidence
      </h2>
      <div className="grid gap-6 lg:grid-cols-2">
        <Column label="A" entries={report.evidence_a} />
        <Column label="B" entries={report.evidence_b} />
      </div>
    </section>
  );
}
