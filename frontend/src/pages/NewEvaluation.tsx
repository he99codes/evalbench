import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";

import { Button, buttonClasses } from "../components/common/Button.tsx";
import { EmptyState, ErrorState, InlineError, LoadingState } from "../components/common/EmptyState.tsx";
import { CriteriaBuilder } from "../components/evaluation/CriteriaBuilder.tsx";
import { PromptEditor } from "../components/evaluation/PromptEditor.tsx";
import { ResponseEditor } from "../components/evaluation/ResponseEditor.tsx";
import { PageHeader } from "../components/layout/AppShell.tsx";
import { useCreateEvaluation } from "../hooks/useEvaluations.ts";
import { useCriteria, useProjects } from "../hooks/useProjects.ts";
import { inputClass, labelClass } from "../lib/utils.ts";
import { evaluationFormSchema, type EvaluationFormValues } from "../lib/validation.ts";

export default function NewEvaluation() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const projects = useProjects();
  const createEvaluation = useCreateEvaluation();

  const form = useForm<EvaluationFormValues>({
    resolver: zodResolver(evaluationFormSchema),
    defaultValues: {
      project_id: searchParams.get("project") ?? "",
      title: "",
      prompt: "",
      response_a: "",
      response_b: "",
      criteria: [],
    },
  });
  const { register, handleSubmit, control, watch, setValue, formState } = form;
  const { fields, replace } = useFieldArray({ control, name: "criteria" });

  const projectId = watch("project_id");
  const promptLength = watch("prompt").length;
  const criteria = useCriteria(projectId || undefined);

  // Default to the first project once projects load.
  useEffect(() => {
    const first = projects.data?.[0];
    if (!projectId && first) setValue("project_id", first.id);
  }, [projects.data, projectId, setValue]);

  // Reset the checklist to the chosen project's enabled criteria at their default weights.
  useEffect(() => {
    if (!criteria.data) return;
    replace(
      criteria.data
        .filter((c) => c.enabled)
        .map((c) => ({ criterion_id: c.id, selected: true, weight: c.weight })),
    );
  }, [criteria.data, replace]);

  const onSubmit = handleSubmit((values) => {
    // Errors surface through createEvaluation.error (rendered below the form).
    createEvaluation.mutate(
      {
      project_id: values.project_id,
      title: values.title.trim(),
      prompt: values.prompt,
      response_a: values.response_a,
      response_b: values.response_b,
      criteria: values.criteria
        .filter((c) => c.selected)
        .map((c) => ({ criterion_id: c.criterion_id, weight: c.weight })),
      },
      { onSuccess: (evaluation) => navigate(`/evaluations/${evaluation.id}`) },
    );
  });

  if (projects.isLoading) return <LoadingState />;
  if (projects.isError) return <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />;
  if (projects.data?.length === 0) {
    return (
      <>
        <PageHeader title="New evaluation" />
        <EmptyState
          title="Create a project first"
          description="Evaluations belong to a project, which holds the rubric criteria."
          action={
            <Link to="/settings" className="text-sm font-medium text-indigo-700 underline">
              Go to Settings
            </Link>
          }
        />
      </>
    );
  }

  const enabledCriteria = criteria.data?.filter((c) => c.enabled) ?? [];

  return (
    <>
      <PageHeader
        title="New evaluation"
        description="Enter a prompt and two candidate responses. Nothing is scored until you run the evaluation."
      />
      <form onSubmit={onSubmit} noValidate className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label htmlFor="project" className={labelClass}>
              Project
            </label>
            <select id="project" className={inputClass} {...register("project_id")}>
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="title" className={labelClass}>
              Title
            </label>
            <input
              id="title"
              className={inputClass}
              aria-invalid={Boolean(formState.errors.title)}
              aria-describedby={formState.errors.title ? "title-error" : undefined}
              {...register("title")}
            />
            {formState.errors.title && (
              <p id="title-error" className="mt-1 text-xs text-red-700">
                {formState.errors.title.message}
              </p>
            )}
          </div>
        </div>

        <PromptEditor
          registration={register("prompt")}
          error={formState.errors.prompt?.message}
          length={promptLength}
        />

        <div className="grid gap-4 md:grid-cols-2">
          <ResponseEditor label="A" registration={register("response_a")} error={formState.errors.response_a?.message} />
          <ResponseEditor label="B" registration={register("response_b")} error={formState.errors.response_b?.message} />
        </div>

        {criteria.isLoading && <LoadingState label="Loading criteria…" />}
        {criteria.isError && <ErrorState error={criteria.error} onRetry={() => void criteria.refetch()} />}
        {criteria.data && enabledCriteria.length === 0 && (
          <EmptyState
            title="This project has no enabled criteria"
            action={
              <Link to={`/projects/${projectId}`} className="text-sm font-medium text-indigo-700 underline">
                Add criteria
              </Link>
            }
          />
        )}
        {enabledCriteria.length > 0 && (
          <CriteriaBuilder
            projectId={projectId}
            criteria={enabledCriteria}
            fields={fields}
            register={register}
            errors={formState.errors}
          />
        )}

        <InlineError error={createEvaluation.error} />

        <div className="flex gap-2">
          <Button type="submit" loading={createEvaluation.isPending} disabled={enabledCriteria.length === 0}>
            Create evaluation
          </Button>
          <Link to="/dashboard" className={buttonClasses("secondary")}>
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}
