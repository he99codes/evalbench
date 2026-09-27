import type { Report } from "../../types/evaluation.ts";

export function ImprovementCard({ improvement }: { improvement: Report["improvement"] }) {
  return (
    <section aria-labelledby="improvement-heading" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
      <h2 id="improvement-heading" className="text-sm font-semibold text-emerald-900">
        Suggested improvement · Response {improvement.target_response}
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-emerald-950">{improvement.improvement}</p>
    </section>
  );
}
