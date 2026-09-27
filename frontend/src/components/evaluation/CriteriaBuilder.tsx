import type { FieldArrayWithId, FieldErrors, UseFormRegister } from "react-hook-form";
import { Link } from "react-router";

import type { EvaluationFormValues } from "../../lib/validation.ts";
import { cn, inputClass } from "../../lib/utils.ts";
import type { Criterion } from "../../types/criterion.ts";

/** Checklist of the project's criteria with a per-evaluation weight for each. */
export function CriteriaBuilder({
  projectId,
  criteria,
  fields,
  register,
  errors,
}: {
  projectId: string;
  criteria: Criterion[];
  fields: FieldArrayWithId<EvaluationFormValues, "criteria">[];
  register: UseFormRegister<EvaluationFormValues>;
  errors: FieldErrors<EvaluationFormValues>;
}) {
  const byId = new Map(criteria.map((c) => [c.id, c]));
  const listError = errors.criteria?.message ?? errors.criteria?.root?.message;

  return (
    <fieldset aria-describedby={listError ? "criteria-error" : undefined}>
      <legend className="mb-1 text-sm font-medium text-slate-700">Criteria and weights</legend>
      <p className="mb-3 text-xs text-slate-500">
        Both responses are scored against the same selected criteria. Weights are saved with this
        evaluation. <Link to={`/projects/${projectId}`} className="text-indigo-700 underline">Manage criteria</Link>
      </p>
      <div className="overflow-hidden rounded-md border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="w-12 px-3 py-2">
                Use
              </th>
              <th scope="col" className="px-3 py-2">
                Criterion
              </th>
              <th scope="col" className="w-20 px-3 py-2">
                Scale
              </th>
              <th scope="col" className="w-28 px-3 py-2">
                Weight
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {fields.map((field, index) => {
              const criterion = byId.get(field.criterion_id);
              if (!criterion) return null;
              const weightError = errors.criteria?.[index]?.weight?.message;
              const checkboxId = `criterion-${criterion.id}`;
              return (
                <tr key={field.id}>
                  <td className="px-3 py-2 align-top">
                    <input
                      id={checkboxId}
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      {...register(`criteria.${index}.selected`)}
                    />
                  </td>
                  <td className="px-3 py-2 align-top">
                    <label htmlFor={checkboxId} className="font-medium text-slate-800">
                      {criterion.name}
                    </label>
                    {criterion.description && (
                      <p className="text-xs text-slate-500">{criterion.description}</p>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top text-slate-600">
                    {criterion.scale_min}–{criterion.scale_max}
                  </td>
                  <td className="px-3 py-2 align-top">
                    <input
                      type="number"
                      step="0.1"
                      min={0}
                      aria-label={`Weight for ${criterion.name}`}
                      aria-invalid={Boolean(weightError)}
                      className={cn(inputClass, "py-1")}
                      {...register(`criteria.${index}.weight`, { valueAsNumber: true })}
                    />
                    {weightError && <p className="mt-1 text-xs text-red-700">{weightError}</p>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {listError && (
        <p id="criteria-error" role="alert" className="mt-2 text-sm text-red-700">
          {listError}
        </p>
      )}
    </fieldset>
  );
}
