import { cn, formatPercent } from "../../lib/utils.ts";
import type { Report } from "../../types/evaluation.ts";

/** Verdict (pairwise preference), backend-computed overall scores and final reasoning. */
export function PreferenceBanner({ report }: { report: Report }) {
  const { preference, summary_a: a, summary_b: b } = report;
  const verdict =
    preference.preferred_response === "TIE" ? "Tie between A and B" : `Response ${preference.preferred_response} preferred`;

  return (
    <section
      aria-labelledby="verdict-heading"
      className="rounded-lg border border-indigo-200 bg-indigo-50 p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">Verdict</p>
          <h2 id="verdict-heading" className="text-2xl font-semibold text-indigo-950">
            {verdict}
          </h2>
          {preference.decisive_criteria.length > 0 && (
            <p className="mt-1 text-sm text-indigo-900">
              Decided by: {preference.decisive_criteria.join(", ")}
            </p>
          )}
        </div>
        <dl className="flex gap-3">
          {[a, b].map((s) => (
            <div
              key={s.label}
              className={cn(
                "min-w-28 rounded-md border bg-white px-4 py-2 text-center",
                preference.preferred_response === s.label ? "border-indigo-400" : "border-slate-200",
              )}
            >
              <dt className="text-xs text-slate-500">Response {s.label}</dt>
              <dd className="text-xl font-semibold tabular-nums text-slate-900">{formatPercent(s.overall_score)}</dd>
              <dd className="text-xs text-slate-500">
                {s.criteria_passed}/{s.criteria_total} criteria passed
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-slate-800">{report.preference.reasoning}</p>
      {!preference.agrees_with_scores && (
        <p className="mt-2 text-xs text-indigo-900">
          Note: the pairwise preference differs from the score leader ({preference.score_leader}).
        </p>
      )}
    </section>
  );
}

/** Shown when the aggregate rubric score diverges from mandatory-requirement compliance. */
export function RewardMismatchBanner({ report }: { report: Report }) {
  const mismatch = report.reward_mismatch;
  if (!mismatch.flagged) return null;
  return (
    <section role="alert" aria-labelledby="mismatch-heading" className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <h2 id="mismatch-heading" className="font-semibold text-amber-900">
        <span aria-hidden="true">⚠ </span>Reward mismatch detected
      </h2>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-amber-900">
        {mismatch.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-amber-800">
        A high rubric score does not mean the task was done as asked. Flagged when the score exceeds
        compliance by {mismatch.threshold} points or more.
      </p>
    </section>
  );
}
