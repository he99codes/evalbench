import type { Criterion, CriterionInput } from "../types/criterion.ts";
import { apiRequest } from "./client.ts";

export const criteriaApi = {
  listForProject: (projectId: string) => apiRequest<Criterion[]>(`/projects/${projectId}/criteria`),
  create: (projectId: string, input: CriterionInput) =>
    apiRequest<Criterion>(`/projects/${projectId}/criteria`, { method: "POST", body: input }),
  update: (id: string, input: Partial<CriterionInput>) =>
    apiRequest<Criterion>(`/criteria/${id}`, { method: "PATCH", body: input }),
  remove: (id: string) => apiRequest<void>(`/criteria/${id}`, { method: "DELETE" }),
};
