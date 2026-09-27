import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";

import { API_BASE_URL, getHealth } from "../api/client.ts";
import { Button } from "../components/common/Button.tsx";
import { EmptyState, ErrorState, InlineError, LoadingState } from "../components/common/EmptyState.tsx";
import { Modal } from "../components/common/Modal.tsx";
import { PageHeader } from "../components/layout/AppShell.tsx";
import { useCreateProject, useDeleteProject, useProjects, useUpdateProject } from "../hooks/useProjects.ts";
import { formatDate, inputClass, labelClass } from "../lib/utils.ts";
import { projectFormSchema, type ProjectFormValues } from "../lib/validation.ts";
import type { Project } from "../types/project.ts";

function ProjectForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: ProjectFormValues;
  submitLabel: string;
  pending: boolean;
  error: unknown;
  onSubmit: (values: ProjectFormValues) => void;
  onCancel?: () => void;
}) {
  const { register, handleSubmit, formState } = useForm<ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues: initial,
  });
  return (
    <form
      noValidate
      className="space-y-3"
      onSubmit={handleSubmit((values) =>
        onSubmit({ name: values.name.trim(), description: values.description }),
      )}
    >
      <div>
        <label htmlFor={`${submitLabel}-project-name`} className={labelClass}>Name</label>
        <input
          id={`${submitLabel}-project-name`}
          className={inputClass}
          aria-invalid={Boolean(formState.errors.name)}
          {...register("name")}
        />
        {formState.errors.name && <p className="mt-1 text-xs text-red-700">{formState.errors.name.message}</p>}
      </div>
      <div>
        <label htmlFor={`${submitLabel}-project-description`} className={labelClass}>Description</label>
        <textarea id={`${submitLabel}-project-description`} rows={2} className={inputClass} {...register("description")} />
      </div>
      <InlineError error={error} />
      <div className="flex justify-end gap-2">
        {onCancel && <Button variant="secondary" onClick={onCancel}>Cancel</Button>}
        <Button type="submit" loading={pending}>{submitLabel}</Button>
      </div>
    </form>
  );
}

function SystemStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth });
  return (
    <section aria-labelledby="system-heading" className="rounded-lg border border-slate-200 p-5">
      <h2 id="system-heading" className="mb-3 text-base font-semibold">System</h2>
      {health.isLoading && <LoadingState />}
      {health.isError && <ErrorState error={health.error} onRetry={() => void health.refetch()} />}
      {health.data && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-sm">
          <dt className="text-slate-500">API</dt>
          <dd className="font-mono">{API_BASE_URL}</dd>
          <dt className="text-slate-500">Status</dt>
          <dd className="font-mono">{health.data.status}</dd>
          <dt className="text-slate-500">Database</dt>
          <dd className="font-mono">{health.data.database}</dd>
          <dt className="text-slate-500">Environment</dt>
          <dd className="font-mono">{health.data.app_env}</dd>
          {health.data.llm_provider && (
            <>
              <dt className="text-slate-500">LLM provider</dt>
              <dd className="font-mono">{health.data.llm_provider}</dd>
              <dt className="text-slate-500">LLM model</dt>
              <dd className="font-mono">{health.data.llm_model}</dd>
            </>
          )}
        </dl>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Provider, model and API keys are configured on the backend via .env and are never sent to the browser.
      </p>
    </section>
  );
}

export default function Settings() {
  const projects = useProjects();
  const createProject = useCreateProject();
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();
  const [editing, setEditing] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [createFormKey, setCreateFormKey] = useState(0);

  const closeEdit = () => {
    setEditing(null);
    updateProject.reset();
  };
  const closeDelete = () => {
    setDeleting(null);
    deleteProject.reset();
  };

  return (
    <>
      <PageHeader title="Settings" description="Projects and system configuration." />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <section aria-labelledby="projects-heading" className="space-y-4">
          <h2 id="projects-heading" className="text-base font-semibold">Projects</h2>
          {projects.isLoading && <LoadingState />}
          {projects.isError && <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />}
          {projects.data?.length === 0 && <EmptyState title="No projects yet" description="Create one below." />}
          {projects.data && projects.data.length > 0 && (
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {projects.data.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <Link to={`/projects/${p.id}`} className="font-medium text-indigo-700 hover:underline">
                      {p.name}
                    </Link>
                    {p.description && <p className="text-xs text-slate-500">{p.description}</p>}
                    <p className="text-xs text-slate-400">Created {formatDate(p.created_at)}</p>
                  </div>
                  <div className="flex gap-1">
                    <Link to={`/projects/${p.id}`} className="rounded-md px-2.5 py-1 text-sm text-slate-700 hover:bg-slate-100">
                      Criteria
                    </Link>
                    <Button variant="ghost" size="sm" onClick={() => setEditing(p)} aria-label={`Edit ${p.name}`}>
                      Edit
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setDeleting(p)} aria-label={`Delete ${p.name}`}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <div className="rounded-lg border border-slate-200 p-4">
            <h3 className="mb-3 text-sm font-semibold">New project</h3>
            <ProjectForm
              key={createFormKey}
              initial={{ name: "", description: "" }}
              submitLabel="Create project"
              pending={createProject.isPending}
              error={createProject.error}
              // Remounting the form (new key) clears it only after a successful create.
              onSubmit={(values) =>
                createProject.mutate(values, { onSuccess: () => setCreateFormKey((k) => k + 1) })
              }
            />
          </div>
        </section>
        <SystemStatus />
      </div>

      <Modal open={editing !== null} onClose={closeEdit} title="Edit project">
        {editing && (
          <ProjectForm
            key={editing.id}
            initial={{ name: editing.name, description: editing.description ?? "" }}
            submitLabel="Save"
            pending={updateProject.isPending}
            error={updateProject.error}
            onCancel={closeEdit}
            onSubmit={(values) => updateProject.mutate({ id: editing.id, input: values }, { onSuccess: closeEdit })}
          />
        )}
      </Modal>

      <Modal
        open={deleting !== null}
        onClose={closeDelete}
        title="Delete project?"
        footer={
          <>
            <Button variant="secondary" onClick={closeDelete}>Cancel</Button>
            <Button
              variant="danger"
              loading={deleteProject.isPending}
              onClick={() => deleting && deleteProject.mutate(deleting.id, { onSuccess: closeDelete })}
            >
              Delete project
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          Deleting “{deleting?.name}” also deletes all of its criteria, evaluations, runs and evidence.
        </p>
        <div className="mt-3">
          <InlineError error={deleteProject.error} />
        </div>
      </Modal>
    </>
  );
}
