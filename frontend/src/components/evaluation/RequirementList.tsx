import { Badge } from "../common/Badge.tsx";
import { cn } from "../../lib/utils.ts";
import type { PromptRequirement, ReportRequirement, RequirementCheck } from "../../types/evaluation.ts";

function Check({ label, check }: { label: "A" | "B"; check: RequirementCheck | null }) {
  if (!check) return <span className="text-slate-400">—</span>;
  return (
    <span
      title={check.explanation}
      className={cn(
        "inline-flex h-6 w-6 items-center justify-center rounded-full text-sm font-bold",
        check.satisfied ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700",
      )}
    >
      <span aria-hidden="true">{check.satisfied ? "✓" : "✗"}</span>
      <span className="sr-only">
        Response {label} {check.satisfied ? "satisfies" : "does not satisfy"} this requirement: {check.explanation}
      </span>
    </span>
  );
}

type Item = (ReportRequirement | PromptRequirement) & { ref?: string };

/** Extracted requests/constraints. With a report, shows per-response compliance marks. */
export function RequirementList({
  requirements,
  ambiguities = [],
}: {
  requirements: Item[];
  ambiguities?: string[];
}) {
  const withChecks = requirements.some((r) => "compliance_a" in r);
  return (
    <section aria-labelledby="requirements-heading" className="rounded-lg border border-slate-200">
      <h2 id="requirements-heading" className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">
        Extracted requirements
      </h2>
      {requirements.length === 0 ? (
        <p className="px-4 py-3 text-sm text-slate-500">No explicit requirements were found in the prompt.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2">Requirement</th>
              {withChecks && (
                <>
                  <th scope="col" className="w-12 px-2 py-2 text-center">A</th>
                  <th scope="col" className="w-12 px-2 py-2 text-center">B</th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {requirements.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {r.ref && <span className="font-mono text-xs text-slate-400">{r.ref}</span>}
                    <Badge tone={r.type === "REQUEST" ? "info" : r.type === "AUDIENCE" ? "neutral" : "warning"}>{r.type}</Badge>
                    {!r.mandatory && <Badge>optional</Badge>}
                  </div>
                  <p className="mt-1 text-slate-800">{r.description}</p>
                </td>
                {"compliance_a" in r && (
                  <>
                    <td className="px-2 py-2 text-center"><Check label="A" check={r.compliance_a} /></td>
                    <td className="px-2 py-2 text-center"><Check label="B" check={r.compliance_b} /></td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ambiguities.length > 0 && (
        <div className="border-t border-slate-200 px-4 py-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ambiguities</h3>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-600">
            {ambiguities.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
