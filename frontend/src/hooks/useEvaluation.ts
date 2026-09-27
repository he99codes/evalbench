import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { ApiError } from "../api/client.ts";
import { evaluationsApi } from "../api/evaluations.ts";
import type { EvaluationRun, EvaluationUpdateInput } from "../types/evaluation.ts";
import { evaluationKeys } from "./useEvaluations.ts";

export const runKeys = {
  list: (evaluationId: string) => ["evaluations", "detail", evaluationId, "runs"] as const,
  report: (evaluationId: string, runId?: string) =>
    ["evaluations", "detail", evaluationId, "report", runId ?? "latest"] as const,
};

const ACTIVE: EvaluationRun["status"][] = ["PENDING", "RUNNING"];

export function useAgreement(evaluationId: string, run1: string | undefined, run2: string | undefined) {
  return useQuery({
    queryKey: ["evaluations", "detail", evaluationId, "agreement", run1 ?? "", run2 ?? ""],
    queryFn: () => evaluationsApi.agreement(evaluationId, run1!, run2!),
    enabled: Boolean(run1 && run2 && run1 !== run2),
  });
}

export function useEvaluation(id: string | undefined) {
  return useQuery({
    queryKey: evaluationKeys.detail(id ?? ""),
    queryFn: () => evaluationsApi.get(id!),
    enabled: Boolean(id),
  });
}

export function useUpdateEvaluation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: EvaluationUpdateInput) => evaluationsApi.update(id, input),
    onSuccess: (evaluation) => {
      qc.setQueryData(evaluationKeys.detail(id), evaluation);
      void qc.invalidateQueries({ queryKey: evaluationKeys.all });
    },
  });
}

/**
 * Runs for an evaluation. Polls every second while the latest run is PENDING/RUNNING,
 * and refreshes the evaluation + report once it reaches a terminal status.
 */
export function useRuns(evaluationId: string | undefined) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: runKeys.list(evaluationId ?? ""),
    queryFn: () => evaluationsApi.runs(evaluationId!),
    enabled: Boolean(evaluationId),
    refetchInterval: (q) => {
      const latest = q.state.data?.at(-1);
      return latest && ACTIVE.includes(latest.status) ? 1000 : false;
    },
  });

  const latest = query.data?.at(-1);
  const previousStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    const before = previousStatus.current;
    previousStatus.current = latest?.status;
    if (evaluationId && before && ACTIVE.includes(before as EvaluationRun["status"]) && latest && !ACTIVE.includes(latest.status)) {
      void qc.invalidateQueries({ queryKey: evaluationKeys.detail(evaluationId) });
      void qc.invalidateQueries({ queryKey: evaluationKeys.all });
    }
  }, [latest?.status, latest, evaluationId, qc]);

  return { ...query, latest, isActive: Boolean(latest && ACTIVE.includes(latest.status)) };
}

export function useStartRun(evaluationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => evaluationsApi.startRun(evaluationId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: runKeys.list(evaluationId) });
      void qc.invalidateQueries({ queryKey: evaluationKeys.detail(evaluationId) });
    },
  });
}

export function useAnalyzePrompt(evaluationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => evaluationsApi.analyzePrompt(evaluationId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: evaluationKeys.detail(evaluationId) }),
  });
}

/** Report for the latest completed run (or `runId`). A 404 simply means "no report yet". */
export function useReport(evaluationId: string | undefined, options: { enabled: boolean; runId?: string }) {
  return useQuery({
    queryKey: runKeys.report(evaluationId ?? "", options.runId),
    queryFn: async () => {
      try {
        return await evaluationsApi.report(evaluationId!, options.runId);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: Boolean(evaluationId) && options.enabled,
  });
}
