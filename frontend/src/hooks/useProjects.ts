import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { criteriaApi } from "../api/criteria.ts";
import { projectsApi } from "../api/projects.ts";
import type { CriterionInput } from "../types/criterion.ts";
import type { ProjectInput } from "../types/project.ts";

export const projectKeys = {
  all: ["projects"] as const,
  detail: (id: string) => ["projects", id] as const,
  criteria: (id: string) => ["projects", id, "criteria"] as const,
};

export function useProjects() {
  return useQuery({ queryKey: projectKeys.all, queryFn: projectsApi.list });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.detail(id ?? ""),
    queryFn: () => projectsApi.get(id!),
    enabled: Boolean(id),
  });
}

export function useProjectAnalytics(id: string | undefined) {
  return useQuery({
    // Under the "evaluations" prefix so any evaluation change refreshes analytics too.
    queryKey: ["evaluations", "analytics", id ?? ""],
    queryFn: () => projectsApi.analytics(id!),
    enabled: Boolean(id),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectInput) => projectsApi.create(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<ProjectInput> }) =>
      projectsApi.update(id, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => projectsApi.remove(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: projectKeys.all });
      void qc.invalidateQueries({ queryKey: ["evaluations"] });
    },
  });
}

// Criteria belong to a project, so their hooks live alongside project hooks.

export function useCriteria(projectId: string | undefined) {
  return useQuery({
    queryKey: projectKeys.criteria(projectId ?? ""),
    queryFn: () => criteriaApi.listForProject(projectId!),
    enabled: Boolean(projectId),
  });
}

export function useCreateCriterion(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CriterionInput) => criteriaApi.create(projectId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.criteria(projectId) }),
  });
}

export function useUpdateCriterion(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<CriterionInput> }) =>
      criteriaApi.update(id, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.criteria(projectId) }),
  });
}

export function useDeleteCriterion(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => criteriaApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.criteria(projectId) }),
  });
}
