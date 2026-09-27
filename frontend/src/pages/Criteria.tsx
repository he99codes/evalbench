import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";

import { Badge } from "../components/common/Badge.tsx";
import { Button } from "../components/common/Button.tsx";
import { EmptyState, ErrorState, InlineError, LoadingState } from "../components/common/EmptyState.tsx";
import { Modal } from "../components/common/Modal.tsx";
import { PageHeader } from "../components/layout/AppShell.tsx";
import {
  useCreateCriterion,
  useCriteria,
  useDeleteCriterion,
  useProject,
  useProjects,
  useUpdateCriterion,
} from "../hooks/useProjects.ts";
import { formatNumber, inputClass, labelClass } from "../lib/utils.ts";
import { criterionFormSchema, type CriterionFormValues } from "../lib/validation.ts";
import type { Criterion } from "../types/criterion.ts";

const emptyCriterion: CriterionFormValues = {
  name: "",
  description: "",
  weight: 1,
  scale_min: 1,
  scale_max: 5,
  enabled: true,
};

function CriterionForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: CriterionFormValues;
  submitLabel: string;
  pending: boolean;
  error: unknown;
  onSubmit: (values: CriterionFormValues) => void;
  onCancel: () => void;
}) {
  const { register, handleSubmit, formState } = useForm<CriterionFormValues>({
    resolver: zodResolver(criterionFormSchema),
    defaultValues: initial,
  });
  const e = formState.errors;

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
      <div>
        <label htmlFor="criterion-name" className={labelClass}>Name</label>
        <input id="criterion-name" className={inputClass} aria-invalid={Boolean(e.name)} {...register("name")} />
        {e.name && <p className="mt-1 text-xs text-red-700">{e.name.message}</p>}
      </div>
      <div>
        <label htmlFor="criterion-description" className={labelClass}>Description</label>
        <textarea id="criterion-description" rows={3} className={inputClass} {...register("description")} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label htmlFor="criterion-weight" className={labelClass}>Default weight</label>
          <input
            id="criterion-weight"
            type="number"
            step="0.1"
            className={inputClass}
            aria-invalid={Boolean(e.weight)}
            {...register("weight", { valueAsNumber: true })}
          />
          {e.weight && <p className="mt-1 text-xs text-red-700">{e.weight.message}</p>}
        </div>
        <div>
          <label htmlFor="criterion-min" className={labelClass}>Scale min</label>
          <input id="criterion-min" type="number" className={inputClass} {...register("scale_min", { valueAsNumber: true })} />
          {e.scale_min && <p className="mt-1 text-xs text-red-700">{e.scale_min.message}</p>}
        </div>
        <div>
          <label htmlFor="criterion-max" className={labelClass}>Scale max</label>
          <input
            id="criterion-max"
            type="number"
            className={inputClass}
            aria-invalid={Boolean(e.scale_max)}
            {...register("scale_max", { valueAsNumber: true })}
          />
          {e.scale_max && <p className="mt-1 text-xs text-red-700">{e.scale_max.message}</p>}
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" className="h-4 w-4 rounded border-slate-300" {...register("enabled")} />
        Enabled (available for new evaluations)
      </label>
      <InlineError error={error} />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={pending}>{submitLabel}</Button>
      </div>
    </form>
  );
}

function ProjectPicker() {
  const projects = useProjects();
  const navigate = useNavigate();

  if (projects.isLoading) return <LoadingState />;
  if (projects.isError) return <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />;

  return (
    <>
      <PageHeader title="Criteria" description="Rubric criteria are managed per project." />
      {projects.data?.length === 0 ? (
        <EmptyState
          title="No projects yet"
          action={<Link to="/settings" className="text-sm font-medium text-indigo-700 underline">Create a project</Link>}
        />
      ) : (
        <div className="max-w-sm">
          <label htmlFor="criteria-project" className={labelClass}>Project</label>
          <select
            id="criteria-project"
            className={inputClass}
            defaultValue=""
            onChange={(e) => e.target.value && navigate(`/projects/${e.target.value}`)}
          >
            <option value="" disabled>Choose a project…</option>
            {projects.data?.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      )}
    </>
  );
}

function ProjectCriteria({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const criteria = useCriteria(projectId);
  const createCriterion = useCreateCriterion(projectId);
  const updateCriterion = useUpdateCriterion(projectId);
  const deleteCriterion = useDeleteCriterion(projectId);

  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Criterion | null>(null);
  const [deleting, setDeleting] = useState<Criterion | null>(null);

  if (project.isLoading || criteria.isLoading) return <LoadingState />;
  if (project.isError) return <ErrorState error={project.error} onRetry={() => void project.refetch()} />;
  if (criteria.isError) return <ErrorState error={criteria.error} onRetry={() => void criteria.refetch()} />;

  const closeAdd = () => {
    setAdding(false);
    createCriterion.reset();
  };
  const closeEdit = () => {
    setEditing(null);
    updateCriterion.reset();
  };
  const closeDelete = () => {
    setDeleting(null);
    deleteCriterion.reset();
  };

  return (
    <>
      <PageHeader
        title={`Criteria · ${project.data?.name ?? ""}`}
        description={project.data?.description ?? "Rubric criteria shared by this project's evaluations."}
        actions={<Button onClick={() => setAdding(true)}>Add criterion</Button>}
      />

      {criteria.data?.length === 0 ? (
        <EmptyState title="No criteria yet" description="Add the criteria both responses will be scored against." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <caption className="sr-only">Criteria for {project.data?.name}</caption>
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-2">Criterion</th>
                <th scope="col" className="px-4 py-2 text-right">Weight</th>
                <th scope="col" className="px-4 py-2">Scale</th>
                <th scope="col" className="px-4 py-2">Status</th>
                <th scope="col" className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {criteria.data?.map((c) => (
                <tr key={c.id}>
                  <td className="px-4 py-2">
                    <p className="font-medium text-slate-800">{c.name}</p>
                    <p className="text-xs text-slate-500">{c.description}</p>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatNumber(c.weight)}</td>
                  <td className="px-4 py-2 text-slate-600">{c.scale_min}–{c.scale_max}</td>
                  <td className="px-4 py-2">
                    <Badge tone={c.enabled ? "success" : "neutral"}>{c.enabled ? "Enabled" : "Disabled"}</Badge>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(c)} aria-label={`Edit ${c.name}`}>
                      Edit
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setDeleting(c)} aria-label={`Delete ${c.name}`}>
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={adding} onClose={closeAdd} title="Add criterion">
        <CriterionForm
          initial={emptyCriterion}
          submitLabel="Add"
          pending={createCriterion.isPending}
          error={createCriterion.error}
          onCancel={closeAdd}
          onSubmit={(values) => createCriterion.mutate(values, { onSuccess: closeAdd })}
        />
      </Modal>

      <Modal open={editing !== null} onClose={closeEdit} title={`Edit ${editing?.name ?? "criterion"}`}>
        {editing && (
          <CriterionForm
            key={editing.id}
            initial={{
              name: editing.name,
              description: editing.description,
              weight: editing.weight,
              scale_min: editing.scale_min,
              scale_max: editing.scale_max,
              enabled: editing.enabled,
            }}
            submitLabel="Save"
            pending={updateCriterion.isPending}
            error={updateCriterion.error}
            onCancel={closeEdit}
            onSubmit={(values) =>
              updateCriterion.mutate({ id: editing.id, input: values }, { onSuccess: closeEdit })
            }
          />
        )}
      </Modal>

      <Modal
        open={deleting !== null}
        onClose={closeDelete}
        title="Delete criterion?"
        footer={
          <>
            <Button variant="secondary" onClick={closeDelete}>Cancel</Button>
            <Button
              variant="danger"
              loading={deleteCriterion.isPending}
              onClick={() => deleting && deleteCriterion.mutate(deleting.id, { onSuccess: closeDelete })}
            >
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">Delete “{deleting?.name}”? This cannot be undone.</p>
        <div className="mt-3">
          <InlineError error={deleteCriterion.error} />
        </div>
      </Modal>
    </>
  );
}

/** /criteria shows a project picker; /projects/:id manages that project's criteria. */
export default function Criteria() {
  const { id } = useParams();
  return id ? <ProjectCriteria projectId={id} /> : <ProjectPicker />;
}
