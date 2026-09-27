import type {
  Agreement,
  AnalyzePromptResponse,
  Evaluation,
  EvaluationCreateInput,
  EvaluationFilters,
  EvaluationRun,
  EvaluationSummary,
  EvaluationUpdateInput,
  Report,
} from "../types/evaluation.ts";
import { apiRequest, apiUrl } from "./client.ts";

export const evaluationsApi = {
  list: (filters: EvaluationFilters = {}) =>
    apiRequest<EvaluationSummary[]>("/evaluations", { query: { ...filters } }),
  get: (id: string) => apiRequest<Evaluation>(`/evaluations/${id}`),
  create: (input: EvaluationCreateInput) =>
    apiRequest<Evaluation>("/evaluations", { method: "POST", body: input }),
  update: (id: string, input: EvaluationUpdateInput) =>
    apiRequest<Evaluation>(`/evaluations/${id}`, { method: "PATCH", body: input }),
  remove: (id: string) => apiRequest<void>(`/evaluations/${id}`, { method: "DELETE" }),

  analyzePrompt: (id: string) =>
    apiRequest<AnalyzePromptResponse>(`/evaluations/${id}/analyze-prompt`, { method: "POST" }),
  startRun: (id: string) => apiRequest<EvaluationRun>(`/evaluations/${id}/run`, { method: "POST" }),
  runs: (id: string) => apiRequest<EvaluationRun[]>(`/evaluations/${id}/runs`),
  report: (id: string, runId?: string) =>
    apiRequest<Report>(`/evaluations/${id}/report`, { query: { run_id: runId } }),
  exportJsonUrl: (id: string) => apiUrl(`/evaluations/${id}/export/json`),
  agreement: (id: string, run1: string, run2: string) =>
    apiRequest<Agreement>(`/evaluations/${id}/agreement`, { query: { run_1: run1, run_2: run2 } }),
};
