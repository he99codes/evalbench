import { useState } from "react";
import { Link } from "react-router";

import { StatusBadge } from "../components/common/Badge.tsx";
import { buttonClasses } from "../components/common/Button.tsx";
import { EmptyState, ErrorState, LoadingState } from "../components/common/EmptyState.tsx";
import { CriterionPassRateChart, PreferenceOverTimeChart } from "../components/evaluation/PreferenceChart.tsx";
import { PageHeader } from "../components/layout/AppShell.tsx";
import { useEvaluations } from "../hooks/useEvaluations.ts";
import { useProjectAnalytics, useProjects } from "../hooks/useProjects.ts";
import { formatDate, formatPercent, inputClass } from "../lib/utils.ts";
import type { ProjectAnalytics } from "../types/project.ts";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</dd>
      {hint && <dd className="mt-0.5 text-xs text-slate-500">{hint}</dd>}
    </div>
  );
}

function AnalyticsSection({ analytics }: { analytics: ProjectAnalytics }) {
  const worst = analytics.most_common_failing_criterion;
  return (
    <section aria-labelledby="analytics-heading" className="mb-8 space-y-4">
      <h2 id="analytics-heading" className="sr-only">Project analytics</h2>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat
          label="Total evaluations"
          value={String(analytics.total_evaluations)}
          hint={`${analytics.completed_evaluations} completed`}
        />
        <Stat label="Response A preferred" value={String(analytics.preference.A)} />
        <Stat
          label="Response B preferred"
          value={String(analytics.preference.B)}
          hint={analytics.preference.TIE ? `${analytics.preference.TIE} tie(s)` : undefined}
        />
        <Stat label="Average quality" value={formatPercent(analytics.average_quality)} hint="Mean weighted score" />
        <Stat
          label="Constraint compliance"
          value={formatPercent(analytics.constraint_compliance_rate)}
          hint={`${analytics.mandatory_checks_satisfied}/${analytics.mandatory_checks_total} mandatory checks`}
        />
      </dl>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
        <span>
          Most common failing criterion:{" "}
          <span className="font-medium text-slate-900">
            {worst ? `${worst.name} (${worst.failed}/${worst.evaluated} failed)` : "none"}
          </span>
        </span>
        <span>
          Reward mismatches flagged: <span className="font-medium text-slate-900">{analytics.reward_mismatch_count}</span>
        </span>
      </div>
      {analytics.completed_evaluations > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <PreferenceOverTimeChart analytics={analytics} />
          <CriterionPassRateChart analytics={analytics} />
        </div>
      )}
    </section>
  );
}

export default function Dashboard() {
  const projects = useProjects();
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const projectId = selected ?? projects.data?.[0]?.id;
  const evaluations = useEvaluations(projectId ? { project_id: projectId } : {});
  const analytics = useProjectAnalytics(projectId);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Aggregate results and evaluations for a project."
        actions={
          <Link to="/evaluations/new" className={buttonClasses()}>
            New evaluation
          </Link>
        }
      />

      {projects.isLoading && <LoadingState />}
      {projects.isError && <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />}
      {projects.data?.length === 0 && (
        <EmptyState
          title="No projects yet"
          action={<Link to="/settings" className="text-sm font-medium text-indigo-700 underline">Create a project</Link>}
        />
      )}

      {projectId && (
        <>
          <div className="mb-4 max-w-xs">
            <label htmlFor="project-filter" className="mb-1 block text-xs font-medium text-slate-600">Project</label>
            <select id="project-filter" className={inputClass} value={projectId} onChange={(e) => setSelected(e.target.value)}>
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          {analytics.isLoading && <LoadingState label="Loading analytics…" />}
          {analytics.isError && <ErrorState error={analytics.error} onRetry={() => void analytics.refetch()} />}
          {analytics.data && <AnalyticsSection analytics={analytics.data} />}

          <h2 className="mb-2 text-base font-semibold text-slate-900">Evaluations</h2>
          {evaluations.isLoading && <LoadingState label="Loading evaluations…" />}
          {evaluations.isError && <ErrorState error={evaluations.error} onRetry={() => void evaluations.refetch()} />}
          {evaluations.data?.length === 0 && (
            <EmptyState
              title="No evaluations yet"
              description="Create an evaluation to compare two responses to the same prompt."
              action={<Link to={`/evaluations/new?project=${projectId}`} className="text-sm font-medium text-indigo-700 underline">Create an evaluation</Link>}
            />
          )}
          {evaluations.data && evaluations.data.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <caption className="sr-only">Evaluations</caption>
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th scope="col" className="px-4 py-2">Title</th>
                    <th scope="col" className="px-4 py-2">Status</th>
                    <th scope="col" className="px-4 py-2">Preferred</th>
                    <th scope="col" className="px-4 py-2 text-right">Score A</th>
                    <th scope="col" className="px-4 py-2 text-right">Score B</th>
                    <th scope="col" className="px-4 py-2">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {evaluations.data.map((e) => (
                    <tr key={e.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2">
                        <Link to={`/evaluations/${e.id}`} className="font-medium text-indigo-700 hover:underline">{e.title}</Link>
                      </td>
                      <td className="px-4 py-2"><StatusBadge status={e.status} /></td>
                      <td className="px-4 py-2">{e.preferred_response ?? "—"}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{formatPercent(e.overall_score_a)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{formatPercent(e.overall_score_b)}</td>
                      <td className="px-4 py-2 text-slate-600">{formatDate(e.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
