import { Badge } from "../common/Badge.tsx";
import { cn, formatNumber, formatPercent } from "../../lib/utils.ts";
import type { CriterionSide, Report } from "../../types/evaluation.ts";

function Cell({ side, max, leads }: { side: CriterionSide; max: number; leads: boolean }) {
  return (
    <td className={cn("px-3 py-2 text-center tabular-nums", leads && "bg-emerald-50")}>
      <span className="font-semibold text-slate-900">{formatNumber(side.score)}</span>
      <span className="text-slate-400">/{max}</span>
      <span className={cn("ml-1.5 text-xs", side.passed ? "text-emerald-700" : "text-red-700")}>
        {side.passed ? "pass" : "fail"}
      </span>
    </td>
  );
}

/** Per-criterion scores for A vs B with weights; totals are the backend's computed aggregates. */
export function ScoreTable({ report }: { report: Report }) {
  return (
    <section aria-labelledby="scores-heading" className="rounded-lg border border-slate-200">
      <h2 id="scores-heading" className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">
        Score matrix
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Criterion scores for responses A and B</caption>
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2">Criterion</th>
              <th scope="col" className="px-3 py-2 text-right">Weight</th>
              <th scope="col" className="px-3 py-2 text-center">Response A</th>
              <th scope="col" className="px-3 py-2 text-center">Response B</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {report.criteria.map((row) => (
              <tr key={row.criterion_id}>
                <th scope="row" className="px-4 py-2 text-left font-medium text-slate-800">
                  {row.name}
                  {row.decisive && (
                    <Badge tone="info" className="ml-2">decisive</Badge>
                  )}
                </th>
                <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                  {formatNumber(row.weight)}
                  <span className="ml-1 text-xs text-slate-400">({formatPercent(row.weight_share * 100, 0)})</span>
                </td>
                <Cell side={row.a} max={row.scale_max} leads={row.leader === "A"} />
                <Cell side={row.b} max={row.scale_max} leads={row.leader === "B"} />
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-slate-200 font-semibold">
            <tr>
              <th scope="row" className="px-4 py-2 text-left">Weighted overall</th>
              <td />
              <td className="px-3 py-2 text-center tabular-nums">{formatPercent(report.summary_a.overall_score)}</td>
              <td className="px-3 py-2 text-center tabular-nums">{formatPercent(report.summary_b.overall_score)}</td>
            </tr>
            <tr className="text-xs font-normal text-slate-600">
              <th scope="row" className="px-4 pb-2 text-left font-normal">Mandatory requirements met</th>
              <td />
              <td className="px-3 pb-2 text-center">
                {report.summary_a.mandatory_satisfied}/{report.summary_a.mandatory_total}
              </td>
              <td className="px-3 pb-2 text-center">
                {report.summary_b.mandatory_satisfied}/{report.summary_b.mandatory_total}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
