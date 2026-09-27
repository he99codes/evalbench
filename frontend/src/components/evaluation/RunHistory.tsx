import { StatusBadge } from "../common/Badge.tsx";
import { cn, formatDate, formatPercent } from "../../lib/utils.ts";
import type { EvaluationRun } from "../../types/evaluation.ts";

/** Every run of this evaluation with reproducibility metadata (Run #1, Run #2, ...). */
export function RunHistory({
  runs,
  selected,
  onToggle,
}: {
  runs: EvaluationRun[];
  selected: string[];
  onToggle: (runId: string) => void;
}) {
  return (
    <section aria-labelledby="runs-heading" className="rounded-lg border border-slate-200">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
        <h2 id="runs-heading" className="text-sm font-semibold text-slate-700">Run history</h2>
        <span className="text-xs text-slate-500">Select two runs to compare</span>
      </div>
      <table className="w-full text-sm">
        <caption className="sr-only">Runs for this evaluation</caption>
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="w-10 px-3 py-2">
              <span className="sr-only">Select</span>
            </th>
            <th scope="col" className="px-2 py-2">Run</th>
            <th scope="col" className="px-2 py-2">Status</th>
            <th scope="col" className="px-2 py-2">Evaluator</th>
            <th scope="col" className="px-2 py-2">Preferred</th>
            <th scope="col" className="px-2 py-2 text-right">Score A</th>
            <th scope="col" className="px-2 py-2 text-right">Score B</th>
            <th scope="col" className="px-2 py-2">Completed</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {runs.map((run, index) => (
            <tr key={run.id} className={cn(selected.includes(run.id) && "bg-indigo-50")}>
              <td className="px-3 py-2">
                <input
                  type="checkbox"
                  aria-label={`Select run #${index + 1} for comparison`}
                  checked={selected.includes(run.id)}
                  disabled={run.status !== "COMPLETED" || (selected.length === 2 && !selected.includes(run.id))}
                  onChange={() => onToggle(run.id)}
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
              </td>
              <td className="px-2 py-2 font-medium text-slate-800">#{index + 1}</td>
              <td className="px-2 py-2"><StatusBadge status={run.status} /></td>
              <td className="px-2 py-2 font-mono text-xs text-slate-600">{run.provider}/{run.evaluator_model}</td>
              <td className="px-2 py-2">{run.outcome?.preferred_response ?? "—"}</td>
              <td className="px-2 py-2 text-right tabular-nums">{formatPercent(run.outcome?.overall_score_a ?? null)}</td>
              <td className="px-2 py-2 text-right tabular-nums">{formatPercent(run.outcome?.overall_score_b ?? null)}</td>
              <td className="px-2 py-2 text-slate-600">{formatDate(run.completed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
