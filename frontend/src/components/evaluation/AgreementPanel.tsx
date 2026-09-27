import { Badge } from "../common/Badge.tsx";
import { formatNumber, formatPercent } from "../../lib/utils.ts";
import type { Agreement } from "../../types/evaluation.ts";

/** Agreement metrics between two runs: same preference, per-criterion score gaps, overall %. */
export function AgreementPanel({ agreement }: { agreement: Agreement }) {
  const { run_1: r1, run_2: r2 } = agreement;
  return (
    <section aria-labelledby="agreement-heading" className="rounded-lg border border-slate-200 p-4">
      <h2 id="agreement-heading" className="mb-3 text-sm font-semibold text-slate-700">
        Evaluator agreement: Run #{r1.run_number} vs Run #{r2.run_number}
      </h2>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-md border border-slate-200 p-3 text-center">
          <p className="text-xs text-slate-500">Preference</p>
          <p className="text-lg font-semibold text-slate-900">{agreement.preference_agrees ? "Agree" : "Disagree"}</p>
          <p className="text-xs text-slate-500">{r1.preferred_response} vs {r2.preferred_response}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 text-center">
          <p className="text-xs text-slate-500">Pass/fail agreement</p>
          <p className="text-lg font-semibold text-slate-900">{formatPercent(agreement.pass_fail_agreement)}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 text-center">
          <p className="text-xs text-slate-500">Overall agreement</p>
          <p className="text-lg font-semibold text-slate-900">{formatPercent(agreement.overall_agreement)}</p>
        </div>
        <div className="rounded-md border border-slate-200 p-3 text-center">
          <p className="text-xs text-slate-500">Mean score gap</p>
          <p className="text-lg font-semibold text-slate-900">
            {agreement.mean_abs_score_difference !== null ? formatPercent(agreement.mean_abs_score_difference * 100) : "—"}
          </p>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
        {!agreement.same_evaluator && <Badge tone="warning">Different evaluators</Badge>}
        {!agreement.same_rubric && <Badge tone="warning">Different rubric versions</Badge>}
        {!agreement.same_prompt_version && <Badge tone="warning">Different prompt versions</Badge>}
        {agreement.criteria_only_in_one_run.length > 0 && (
          <Badge tone="warning">Not compared: {agreement.criteria_only_in_one_run.join(", ")}</Badge>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Per-criterion score differences between the two runs</caption>
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-2 py-1">Criterion</th>
              <th scope="col" className="px-2 py-1">Response</th>
              <th scope="col" className="px-2 py-1 text-right">Run #{r1.run_number}</th>
              <th scope="col" className="px-2 py-1 text-right">Run #{r2.run_number}</th>
              <th scope="col" className="px-2 py-1 text-right">Difference</th>
              <th scope="col" className="px-2 py-1">Pass/fail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {agreement.criteria.map((c) => (
              <tr key={`${c.criterion_id}-${c.response}`}>
                <td className="px-2 py-1 font-medium text-slate-800">{c.name}</td>
                <td className="px-2 py-1">{c.response}</td>
                <td className="px-2 py-1 text-right tabular-nums">{formatNumber(c.score_1)}/{c.scale_max}</td>
                <td className="px-2 py-1 text-right tabular-nums">{formatNumber(c.score_2)}/{c.scale_max}</td>
                <td className="px-2 py-1 text-right tabular-nums">{formatPercent(c.normalized_difference * 100, 0)}</td>
                <td className="px-2 py-1">{c.pass_agrees ? "agree" : "disagree"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
