import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { StatusBadge } from "../components/common/Badge.tsx";
import { Button, buttonClasses } from "../components/common/Button.tsx";
import { ErrorState, InlineError, LoadingState } from "../components/common/EmptyState.tsx";
import { Modal } from "../components/common/Modal.tsx";
import { EvidencePanel } from "../components/evaluation/EvidencePanel.tsx";
import { ImprovementCard } from "../components/evaluation/ImprovementCard.tsx";
import { PreferenceBanner, RewardMismatchBanner } from "../components/evaluation/PreferenceBanner.tsx";
import { AgreementPanel } from "../components/evaluation/AgreementPanel.tsx";
import { RequirementList } from "../components/evaluation/RequirementList.tsx";
import { RunHistory } from "../components/evaluation/RunHistory.tsx";
import { ScoreTable } from "../components/evaluation/ScoreTable.tsx";
import { PageHeader } from "../components/layout/AppShell.tsx";
import { evaluationsApi } from "../api/evaluations.ts";
import {
  useAgreement,
  useAnalyzePrompt,
  useEvaluation,
  useReport,
  useRuns,
  useStartRun,
} from "../hooks/useEvaluation.ts";
import { useDeleteEvaluation } from "../hooks/useEvaluations.ts";
import { useProject } from "../hooks/useProjects.ts";
import { formatDate, formatNumber } from "../lib/utils.ts";
import type { Evaluation, EvaluationRun, Report } from "../types/evaluation.ts";

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  requirement_extraction: "1/5 Extracting requirements",
  independent_evaluation: "2/5 Scoring A and B independently",
  pairwise_comparison: "3/5 Pairwise comparison",
  improvement: "4/5 Generating improvement",
  reward_mismatch: "5/5 Checking constraint compliance",
};

function TextBlock({ title, text }: { title: string; text: string }) {
  return (
    <section aria-label={title} className="rounded-lg border border-slate-200">
      <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700">{title}</h2>
      <p className="whitespace-pre-wrap px-4 py-3 font-mono text-sm leading-relaxed text-slate-800">{text}</p>
    </section>
  );
}

function SelectedCriteria({ evaluation }: { evaluation: Evaluation }) {
  return (
    <section aria-labelledby="criteria-heading">
      <h2 id="criteria-heading" className="mb-2 text-base font-semibold text-slate-900">Selected criteria</h2>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="px-4 py-2">Criterion</th>
              <th scope="col" className="px-4 py-2">Scale</th>
              <th scope="col" className="px-4 py-2 text-right">Weight</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {evaluation.criteria.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-2">
                  <p className="font-medium text-slate-800">{c.criterion.name}</p>
                  <p className="text-xs text-slate-500">{c.criterion.description}</p>
                </td>
                <td className="px-4 py-2 text-slate-600">{c.criterion.scale_min}–{c.criterion.scale_max}</td>
                <td className="px-4 py-2 text-right tabular-nums">{formatNumber(c.weight)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RunProgressPanel({ run }: { run: EvaluationRun }) {
  const { completed_steps: done, total_steps: total, stage } = run.progress;
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div role="status" aria-live="polite" className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-amber-900">
          Running · {STAGE_LABELS[stage ?? "queued"] ?? stage}
        </span>
        <span className="tabular-nums text-amber-800">{done}/{total} LLM calls</span>
      </div>
      <div
        role="progressbar"
        aria-label="Evaluation progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="mt-2 h-2 overflow-hidden rounded-full bg-amber-100"
      >
        <div className="h-full bg-amber-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function FailedRunPanel({ run, onRetry, retrying }: { run: EvaluationRun; onRetry: () => void; retrying: boolean }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <p className="font-semibold">The last run failed{run.error?.stage ? ` during ${run.error.stage.replaceAll("_", " ")}` : ""}.</p>
      <p className="mt-1 break-words">{run.error?.message ?? "Unknown error"}</p>
      <p className="mt-1 text-xs text-red-800">No scores were recorded for this run.</p>
      <Button variant="danger" size="sm" className="mt-3" loading={retrying} onClick={onRetry}>
        Retry run
      </Button>
    </div>
  );
}

function RunMeta({ run }: { run: Report["run"] }) {
  const items: [string, string][] = [
    ["Evaluator", `${run.provider} / ${run.evaluator_model}`],
    ["Rubric version", run.rubric_version],
    ["Prompt version", run.prompt_version],
    ["Candidate order", run.candidate_order === "BA" ? "B shown first" : run.candidate_order === "AB" ? "A shown first" : "—"],
    ["Latency", run.latency_ms !== null ? `${(run.latency_ms / 1000).toFixed(1)} s` : "—"],
    ["Tokens (in / out)", run.input_tokens !== null ? `${run.input_tokens} / ${run.output_tokens}` : "—"],
    ["Completed", formatDate(run.completed_at)],
  ];
  return (
    <section aria-labelledby="run-meta-heading" className="rounded-lg border border-slate-200 p-4">
      <h2 id="run-meta-heading" className="mb-2 text-sm font-semibold text-slate-700">Run metadata</h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
        {items.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-slate-500">{k}</dt>
            <dd className="break-all font-mono text-slate-800">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function EvaluationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const evaluation = useEvaluation(id);
  const project = useProject(evaluation.data?.project_id);
  const runs = useRuns(id);
  const hasCompletedRun = Boolean(runs.data?.some((r) => r.status === "COMPLETED"));
  const report = useReport(id, { enabled: hasCompletedRun });
  const startRun = useStartRun(id ?? "");
  const analyze = useAnalyzePrompt(id ?? "");
  const deleteEvaluation = useDeleteEvaluation();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]);
  const agreement = useAgreement(id ?? "", selectedRuns[0], selectedRuns[1]);

  const toggleRun = (runId: string) =>
    setSelectedRuns((prev) =>
      prev.includes(runId) ? prev.filter((r) => r !== runId) : prev.length < 2 ? [...prev, runId] : prev,
    );

  if (evaluation.isLoading) return <LoadingState label="Loading evaluation…" />;
  if (evaluation.isError) return <ErrorState error={evaluation.error} onRetry={() => void evaluation.refetch()} />;
  const data = evaluation.data;
  if (!data) return null;

  const latest = runs.latest;
  const running = runs.isActive || data.status === "RUNNING" || startRun.isPending;
  const reportData = report.data ?? null;

  return (
    <>
      <PageHeader
        title={data.title}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            {project.data && (
              <Link to={`/projects/${project.data.id}`} className="text-indigo-700 hover:underline">{project.data.name}</Link>
            )}
            <span>Created {formatDate(data.created_at)}</span>
          </span>
        }
        actions={
          <>
            <Button variant="secondary" onClick={() => analyze.mutate()} loading={analyze.isPending} disabled={running}>
              Analyze prompt
            </Button>
            <Button onClick={() => startRun.mutate()} loading={running} disabled={running}>
              {running ? "Running…" : hasCompletedRun ? "Re-run evaluation" : "Run evaluation"}
            </Button>
            {reportData && (
              <a href={evaluationsApi.exportJsonUrl(data.id)} className={buttonClasses("secondary")} download>
                Export JSON
              </a>
            )}
            <Button variant="ghost" onClick={() => setConfirmDelete(true)} disabled={running}>
              Delete
            </Button>
          </>
        }
      />

      <div className="space-y-6">
        <InlineError error={startRun.error ?? analyze.error} />
        {runs.isError && <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />}
        {latest && runs.isActive && <RunProgressPanel run={latest} />}
        {latest?.status === "FAILED" && !running && (
          <FailedRunPanel run={latest} retrying={startRun.isPending} onRetry={() => startRun.mutate()} />
        )}
        {report.isLoading && <LoadingState label="Loading report…" />}
        {report.isError && <ErrorState error={report.error} onRetry={() => void report.refetch()} />}

        {reportData ? (
          <>
            <PreferenceBanner report={reportData} />
            <RewardMismatchBanner report={reportData} />
            <TextBlock title="Prompt" text={reportData.evaluation.prompt} />
            <div className="grid gap-4 lg:grid-cols-2">
              <TextBlock title="Response A" text={reportData.evaluation.response_a} />
              <TextBlock title="Response B" text={reportData.evaluation.response_b} />
            </div>
            <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
              <RequirementList requirements={reportData.requirements} ambiguities={reportData.ambiguities} />
              <div className="space-y-4">
                <ImprovementCard improvement={reportData.improvement} />
                <RunMeta run={reportData.run} />
              </div>
            </div>
            <ScoreTable report={reportData} />
            <EvidencePanel report={reportData} />
            {runs.data && runs.data.length > 0 && (
              <RunHistory runs={runs.data} selected={selectedRuns} onToggle={toggleRun} />
            )}
            {agreement.isLoading && <LoadingState label="Comparing runs…" />}
            {agreement.isError && <ErrorState error={agreement.error} onRetry={() => void agreement.refetch()} />}
            {agreement.data && <AgreementPanel agreement={agreement.data} />}
          </>
        ) : (
          <>
            <TextBlock title="Prompt" text={data.prompt} />
            <div className="grid gap-4 lg:grid-cols-2">
              <TextBlock title="Response A" text={data.response_a} />
              <TextBlock title="Response B" text={data.response_b} />
            </div>
            {data.requirements.length > 0 && (
              <RequirementList requirements={data.requirements} ambiguities={analyze.data?.ambiguities} />
            )}
            <SelectedCriteria evaluation={data} />
          </>
        )}
      </div>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Delete evaluation?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button
              variant="danger"
              loading={deleteEvaluation.isPending}
              onClick={() => deleteEvaluation.mutate(data.id, { onSuccess: () => navigate("/dashboard") })}
            >
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          This permanently deletes “{data.title}” and all of its runs, scores and evidence.
        </p>
        <div className="mt-3">
          <InlineError error={deleteEvaluation.error} />
        </div>
      </Modal>
    </>
  );
}
