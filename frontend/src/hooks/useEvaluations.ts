import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { evaluationsApi } from "../api/evaluations.ts";
import type { EvaluationCreateInput, EvaluationFilters } from "../types/evaluation.ts";

export const evaluationKeys = {
  all: ["evaluations"] as const,
  list: (filters: EvaluationFilters) => ["evaluations", "list", filters] as const,
  detail: (id: string) => ["evaluations", "detail", id] as const,
};

export function useEvaluations(filters: EvaluationFilters = {}) {
  return useQuery({
    queryKey: evaluationKeys.list(filters),
    queryFn: () => evaluationsApi.list(filters),
  });
}

export function useCreateEvaluation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: EvaluationCreateInput) => evaluationsApi.create(input),
    onSuccess: (evaluation) => {
      qc.setQueryData(evaluationKeys.detail(evaluation.id), evaluation);
      void qc.invalidateQueries({ queryKey: evaluationKeys.all });
    },
  });
}

export function useDeleteEvaluation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => evaluationsApi.remove(id),
    onSuccess: (_, id) => {
      qc.removeQueries({ queryKey: evaluationKeys.detail(id) });
      void qc.invalidateQueries({ queryKey: evaluationKeys.all });
    },
  });
}
